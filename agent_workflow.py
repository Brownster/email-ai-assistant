import json
import logging
from datetime import datetime
from json import JSONDecodeError
from abc import ABC, abstractmethod

# LangChain and OpenAI
from langchain.llms import OpenAI
from langchain import PromptTemplate, LLMChain
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema import OutputParserException

# Tenacity for retrying on output parser errors
from tenacity import retry, stop_after_attempt, retry_if_exception_type

# Presidio libraries for PII redaction
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

# ---------------------------
# Logging configuration
# ---------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------
# Utility Functions
# ---------------------------
def safe_json_loads(data):
    try:
        return json.loads(data)
    except JSONDecodeError:
        return {"error": "Invalid JSON output from agent"}

def format_reviewer_analysis(data):
    # Convert the structured output into natural language for the department agent
    return (
        f"Sentiment: {data.get('sentiment', 'N/A')}\n"
        f"Urgency: {data.get('urgency', 'N/A')}/10\n"
        f"Department: {data.get('department', 'N/A')}\n"
        f"Review: {data.get('review', 'N/A')}"
    )

VALID_DEPARTMENTS = {"customer_service", "sales", "spam"}
VALID_ACTIONS = {"auto_respond", "escalate", "use_tool"}

def validate_reviewer_output(reviewer_output):
    # Ensure the department is valid; default to customer_service if not.
    department = reviewer_output.get("department", "").lower()
    if department not in VALID_DEPARTMENTS:
        reviewer_output["department"] = "customer_service"
    return reviewer_output

def validate_department_decision(decision):
    action = decision.get("action", "").lower()
    if action not in VALID_ACTIONS:
        return {"action": "escalate", "details": "Invalid action requested"}
    return decision

def validate_draft(draft):
    # Ensure confidence is a float between 0 and 1
    try:
        conf = float(draft.get("confidence", 0))
    except (ValueError, TypeError):
        conf = 0.0
    draft["confidence"] = max(0.0, min(1.0, conf))
    return draft

# ---------------------------
# Improved PII Redaction
# ---------------------------
def redact_email(content: str) -> str:
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    results = analyzer.analyze(text=content, language="en")
    # Use presidio-anonymizer to properly redact all detected PII in one go.
    return anonymizer.anonymize(text=content, analyzer_results=results).text

# ---------------------------
# LLM Output Retries
# ---------------------------
@retry(
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(OutputParserException)
)
def reliable_chain_execution(chain, **kwargs):
    return chain.run(**kwargs)

# ---------------------------
# Initialize the LLM
# ---------------------------
llm = OpenAI(temperature=0.7)  # Ensure your OPENAI_API_KEY is set in the environment

# ---------------------------
# 1. Email Reviewer Agent (with Structured Output)
# ---------------------------
reviewer_schemas = [
    ResponseSchema(name="sentiment", description="positive, negative, or neutral"),
    ResponseSchema(name="urgency", description="A number between 1 and 10 representing urgency"),
    ResponseSchema(name="department", description="customer_service, sales, or spam"),
    ResponseSchema(name="review", description="A brief analysis summary of the email")
]
reviewer_parser = StructuredOutputParser.from_response_schemas(reviewer_schemas)

email_reviewer_template = """
You are an Email Reviewer agent. Analyze the following email for sentiment, urgency, and potential spam.
Also determine which department should handle this email (customer_service, sales) or if it should be flagged as spam.

Email:
{email_content}
"""

email_reviewer_prompt = PromptTemplate(
    template=email_reviewer_template + "\n{format_instructions}",
    input_variables=["email_content"],
    partial_variables={"format_instructions": reviewer_parser.get_format_instructions()}
)

email_reviewer_chain = LLMChain(
    llm=llm,
    prompt=email_reviewer_prompt,
    output_parser=reviewer_parser
)

# ---------------------------
# 2. Department Agent (with examples and Structured Output)
# ---------------------------
department_schemas = [
    ResponseSchema(name="action", description="auto_respond, escalate, or use_tool"),
    ResponseSchema(name="details", description="Additional instructions")
]
department_parser = StructuredOutputParser.from_response_schemas(department_schemas)

department_agent_template = """
You are a {department} agent. Here are some example decisions for your department:
- For customer_service: respond with "escalate" for refund requests, or "auto_respond" for tracking inquiries.
- For sales: respond with "use_tool" to check the CRM, or "auto_respond" with promotional codes.

Given the email below and the reviewer's analysis, decide what action should be taken.
Possible actions are: "auto_respond", "escalate", or "use_tool".

Email:
{email_content}

Reviewer Analysis:
{reviewer_analysis}
"""

department_agent_prompt = PromptTemplate(
    template=department_agent_template + "\n{format_instructions}",
    input_variables=["department", "email_content", "reviewer_analysis"],
    partial_variables={"format_instructions": department_parser.get_format_instructions()}
)

department_agent_chain = LLMChain(
    llm=llm,
    prompt=department_agent_prompt,
    output_parser=department_parser
)

# ---------------------------
# 3. Email Drafter Agent (with Structured Output)
# ---------------------------
drafter_schemas = [
    ResponseSchema(name="draft_email", description="The full text of the draft reply."),
    ResponseSchema(name="sentiment", description="The sentiment of the reply: positive, negative, or neutral."),
    ResponseSchema(name="confidence", description="A numeric confidence score between 0 and 1."),
    ResponseSchema(name="review", description="Brief commentary on the draft's quality and appropriateness.")
]
drafter_parser = StructuredOutputParser.from_response_schemas(drafter_schemas)

email_drafter_template = """
You are an Email Drafter agent. Based on the following department decision and the original email,
draft a professional reply that addresses the customer's concerns.
Include a sentiment analysis, a confidence score (between 0 and 1), and a brief review of your reply.

Department Decision:
{department_details}

Email:
{email_content}
"""

email_drafter_prompt = PromptTemplate(
    template=email_drafter_template + "\n{format_instructions}",
    input_variables=["department_details", "email_content"],
    partial_variables={"format_instructions": drafter_parser.get_format_instructions()}
)

email_drafter_chain = LLMChain(
    llm=llm,
    prompt=email_drafter_prompt,
    output_parser=drafter_parser
)

# ---------------------------
# 4. Final Optimized Workflow Function
# ---------------------------
def process_email(email_content: str) -> dict:
    try:
        # PII Redaction
        cleaned_email = redact_email(email_content)
        logger.info("Email content redacted.")

        # Step 1: Email Reviewer Agent with retry on output errors
        reviewer_response = reliable_chain_execution(email_reviewer_chain, email_content=cleaned_email)
        reviewer_output = safe_json_loads(reviewer_response)
        reviewer_output = validate_reviewer_output(reviewer_output)
        logger.info(f"Reviewer Output: {reviewer_output}")

        # Step 2: Department Agent Decision
        department = reviewer_output.get("department")
        formatted_reviewer = format_reviewer_analysis(reviewer_output)
        department_response = reliable_chain_execution(
            department_agent_chain,
            department=department,
            email_content=cleaned_email,
            reviewer_analysis=formatted_reviewer
        )
        department_decision = validate_department_decision(safe_json_loads(department_response))
        logger.info(f"Department Decision: {department_decision}")

        # Step 3: Email Drafter Agent
        drafter_response = reliable_chain_execution(
            email_drafter_chain,
            department_details=json.dumps(department_decision),
            email_content=cleaned_email
        )
        draft_output = safe_json_loads(drafter_response)
        draft_output = validate_draft(draft_output)
        logger.info(f"Draft Output: {draft_output}")

        # Aggregate results with metadata
        result = {
            "metadata": {
                "workflow_version": "1.1",
                "timestamp": datetime.now().isoformat()
            },
            "reviewer_analysis": reviewer_output,
            "department_decision": department_decision,
            "draft_reply": draft_output
        }
        return result

    except Exception as e:
        logger.error(f"Failed processing email: {str(e)}")
        return {"error": "Processing failed"}

# ---------------------------
# Async Support Version
# ---------------------------
async def process_email_async(email_content: str) -> dict:
    try:
        cleaned_email = redact_email(email_content)
        reviewer_response = await email_reviewer_chain.arun(email_content=cleaned_email)
        reviewer_output = safe_json_loads(reviewer_response)
        reviewer_output = validate_reviewer_output(reviewer_output)

        department = reviewer_output.get("department")
        formatted_reviewer = format_reviewer_analysis(reviewer_output)
        department_response = await department_agent_chain.arun(
            department=department,
            email_content=cleaned_email,
            reviewer_analysis=formatted_reviewer
        )
        department_decision = validate_department_decision(safe_json_loads(department_response))

        drafter_response = await email_drafter_chain.arun(
            department_details=json.dumps(department_decision),
            email_content=cleaned_email
        )
        draft_output = safe_json_loads(drafter_response)
        draft_output = validate_draft(draft_output)

        return {
            "metadata": {
                "workflow_version": "1.1",
                "timestamp": datetime.now().isoformat()
            },
            "reviewer_analysis": reviewer_output,
            "department_decision": department_decision,
            "draft_reply": draft_output
        }
    except Exception as e:
        logger.error(f"Async processing failed: {str(e)}")
        return {"error": "Async processing failed"}

# ---------------------------
# Agent Chaining (Optional)
# ---------------------------
chain = (
    RunnablePassthrough() 
    | email_reviewer_chain 
    | department_agent_chain 
    | email_drafter_chain
)

# ---------------------------
# Integration Readiness: Abstract EmailProcessor
# ---------------------------
class EmailProcessor(ABC):
    @abstractmethod
    def process(self, email_content: str) -> dict:
        pass

class LangChainProcessor(EmailProcessor):
    def __init__(self):
        # You can choose to initialize your chain here.
        # In this example, we reuse the process_email function.
        pass

    def process(self, email_content: str) -> dict:
        return process_email(email_content)

# ---------------------------
# Unit Testing Strategy
# ---------------------------
import unittest

class TestEmailWorkflow(unittest.TestCase):
    def test_negative_sentiment(self):
        email = "Your service is terrible! I want a refund immediately!"
        result = process_email(email)
        reviewer = result.get("reviewer_analysis", {})
        department = result.get("department_decision", {})
        # For this example, assume negative sentiment is recognized as "negative"
        self.assertEqual(reviewer.get("sentiment"), "negative")
        # Urgency should be high (>= 7) for strongly negative language
        self.assertGreaterEqual(int(reviewer.get("urgency", 0)), 7)
        # Expect the department agent to decide to escalate for refund requests
        self.assertEqual(department.get("action"), "escalate")

if __name__ == "__main__":
    # Run the unit tests
    unittest.main(verbosity=2, exit=False)

    # Or process a sample email if not testing:
    sample_email = (
        "Subject: Issue with my recent order\n\n"
        "I am very disappointed with the delivery. The package arrived late and the item appears damaged. "
        "I need help resolving this issue as soon as possible."
    )
    result = process_email(sample_email)
    print("Final Workflow Result:")
    print(json.dumps(result, indent=2))
