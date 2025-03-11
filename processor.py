import json
import boto3
import email
import os
import uuid
import time
import logging
import argparse
from email import policy
from email.parser import BytesParser
from botocore.exceptions import ClientError
from datetime import datetime
from botocore.config import Config
import psycopg2
from psycopg2.extras import Json, DictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Email body size limit to prevent DB storage issues
MAX_BODY_LENGTH = 100000

def truncate_body(body):
    return body[:MAX_BODY_LENGTH] if body else ""

class EmailProcessor:
    def __init__(self, config_path=None, db_connection_string=None):
        self.config = self._load_config(config_path) if config_path else {}
        
        # Initialize DB connection
        if db_connection_string:
            self.db_conn = psycopg2.connect(db_connection_string)
        else:
            # Default to environment variables if connection string not provided
            self.db_conn = psycopg2.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                database=os.environ.get("DB_NAME", "email_assistant"),
                user=os.environ.get("DB_USER", "postgres"),
                password=os.environ.get("DB_PASSWORD", "postgres"),
                port=os.environ.get("DB_PORT", "5432")
            )
        
        # Initialize S3 client if S3 storage is enabled
        self.use_s3 = self.config.get('use_s3', False)
        if self.use_s3:
            self.s3 = boto3.client('s3')
            self.s3_bucket = self.config.get('s3_bucket', 'email-attachments')
        
        # Cache for mailbox configuration
        self.mailbox_cache = {'timestamp': 0, 'config': None}
        self.cache_ttl = 300  # 5 minutes

    def _load_config(self, config_path):
        """Load configuration from a JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def get_mailbox_config(self):
        """Get mailbox configuration either from cache or database"""
        now = time.time()
        if now - self.mailbox_cache['timestamp'] < self.cache_ttl and self.mailbox_cache['config']:
            return self.mailbox_cache['config']
        
        try:
            cursor = self.db_conn.cursor(cursor_factory=DictCursor)
            cursor.execute("SELECT name, email_alias, description FROM departments")
            rows = cursor.fetchall()
            
            mailboxes = []
            for row in rows:
                if row['email_alias']:
                    mailboxes.append({
                        'email': row['email_alias'],
                        'type': row['name'].lower(),
                        'description': row['description']
                    })
            
            config_value = {"mailboxes": mailboxes}
            cursor.close()
        except Exception as e:
            logger.error(f"Error retrieving mailbox config from database: {e}")
            config_value = {"mailboxes": []}
        
        self.mailbox_cache = {'timestamp': now, 'config': config_value}
        return config_value

    def is_valid_mailbox(self, recipient_email):
        """Check if the recipient email belongs to a configured mailbox"""
        config = self.get_mailbox_config()
        for mailbox in config.get('mailboxes', []):
            if mailbox.get('email') == recipient_email:
                return True, mailbox.get('type', 'default')
        return False, None

    def extract_email_content(self, raw_email):
        """Parse raw email and extract relevant content"""
        try:
            msg = BytesParser(policy=policy.default).parsebytes(raw_email)
            
            # Extract basic headers
            email_data = {
                'external_id': msg.get('Message-ID', ''),
                'subject': msg.get('subject', ''),
                'from_address': msg.get('from', ''),
                'from_name': self._extract_name_from_email_header(msg.get('from', '')),
                'to_address': msg.get('to', ''),
                'received_timestamp': datetime.now(),
                'thread_id': msg.get('References', msg.get('In-Reply-To', ''))
            }
            
            # Extract CC and BCC
            cc = msg.get('cc', '')
            bcc = msg.get('bcc', '')
            email_data['cc_addresses'] = self._parse_email_list(cc) if cc else []
            email_data['bcc_addresses'] = self._parse_email_list(bcc) if bcc else []
            
            # Extract body content (prefer HTML, fallback to plain text)
            if msg.is_multipart():
                email_data['body_html'] = ""
                email_data['body_text'] = ""
                
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    
                    # Skip attachments
                    if "attachment" in content_disposition:
                        continue
                    
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            decoded_content = payload.decode('utf-8', errors='replace')
                            
                            if content_type == "text/plain":
                                email_data['body_text'] = truncate_body(decoded_content)
                            elif content_type == "text/html":
                                email_data['body_html'] = truncate_body(decoded_content)
                    except Exception as e:
                        logger.warning(f"Error decoding email part: {e}")
            else:
                # Not multipart, just extract the content
                content_type = msg.get_content_type()
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        decoded_content = payload.decode('utf-8', errors='replace')
                        
                        if content_type == "text/plain":
                            email_data['body_text'] = truncate_body(decoded_content)
                            email_data['body_html'] = ""
                        elif content_type == "text/html":
                            email_data['body_html'] = truncate_body(decoded_content)
                            email_data['body_text'] = ""
                        else:
                            email_data['body_text'] = truncate_body(decoded_content)
                            email_data['body_html'] = ""
                except Exception as e:
                    logger.warning(f"Error decoding email content: {e}")
                    email_data['body_text'] = ""
                    email_data['body_html'] = ""
            
            # Extract attachments metadata
            attachments = []
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                
                content_disposition = part.get("Content-Disposition", None)
                if content_disposition and "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        attachment_data = {
                            'filename': filename,
                            'content_type': part.get_content_type(),
                            'size': len(part.get_payload(decode=True))
                        }
                        
                        # Store attachment if S3 is enabled
                        if self.use_s3:
                            attachment_data['storage_path'] = self._store_attachment_s3(
                                part.get_payload(decode=True),
                                filename,
                                email_data.get('external_id', '')
                            )
                        
                        attachments.append(attachment_data)
            
            email_data['attachments'] = attachments
            
            # Set default values for the new DB schema
            email_data['status'] = 'pending_review'
            email_data['is_read'] = False
            email_data['priority'] = 'normal'
            
            # Additional metadata
            email_data['metadata'] = {
                'raw_headers': {k: v for k, v in msg.items()},
                'processing_time': datetime.now().isoformat()
            }
            
            return email_data
        
        except Exception as e:
            logger.error(f"Error parsing email: {e}")
            raise

    def _extract_name_from_email_header(self, header):
        """Extract name from email header (e.g., 'John Doe <john@example.com>')"""
        if not header:
            return ''
        
        if '<' in header:
            return header.split('<')[0].strip()
        return ''

    def _parse_email_list(self, email_string):
        """Parse comma-separated email addresses into a list"""
        if not email_string:
            return []
        
        # Simple split by comma, more sophisticated parsing could be implemented
        return [addr.strip() for addr in email_string.split(',')]

    def _store_attachment_s3(self, content, filename, message_id):
        """Store attachment in S3 bucket"""
        try:
            key = f"attachments/{message_id}/{uuid.uuid4()}-{filename}"
            self.s3.put_object(
                Bucket=self.s3_bucket,
                Key=key,
                Body=content
            )
            return key
        except Exception as e:
            logger.error(f"Error storing attachment in S3: {e}")
            return None

    def _get_llm_provider(self):
        """Get available LLM provider from database"""
        try:
            cursor = self.db_conn.cursor(cursor_factory=DictCursor)
            cursor.execute(
                "SELECT provider_id, name, provider_type, config FROM llm_providers WHERE is_active = TRUE LIMIT 1"
            )
            provider = cursor.fetchone()
            cursor.close()
            
            if provider:
                return provider
            return None
        except Exception as e:
            logger.error(f"Error getting LLM provider: {e}")
            return None

    def simulate_llm_response(self, email_data, mailbox_type):
        """
        Simulate LLM response based on email content and mailbox type.
        In production, replace this function with an actual LLM API call.
        """
        subject = email_data.get('subject', 'No Subject')
        sender = email_data.get('from_name', 'Customer')
        
        # Get LLM provider (in production, use this to call the actual LLM API)
        provider = self._get_llm_provider()
        provider_id = provider['provider_id'] if provider else None
        provider_type = provider['provider_type'] if provider else 'simulated'
        
        # Adjust response based on mailbox type
        if mailbox_type == 'support':
            return {
                'subject': f"Re: {subject}",
                'body_text': f"Thank you for contacting our support team regarding '{subject}'.\n\nWe've received your request and will be in touch within 24 hours.\n\nBest regards,\nSupport Team",
                'body_html': f"<p>Thank you for contacting our support team regarding '{subject}'.</p><p>We've received your request and will be in touch within 24 hours.</p><p>Best regards,<br>Support Team</p>",
                'confidence': 0.85,
                'llm_provider_id': provider_id,
                'llm_model': 'simulated-model'
            }
        elif mailbox_type == 'sales':
            return {
                'subject': f"Re: {subject}",
                'body_text': f"Thank you for your interest, {sender}.\n\nI appreciate your inquiry about '{subject}'. Let's schedule a call to discuss your needs further.\n\nBest regards,\nSales Team",
                'body_html': f"<p>Thank you for your interest, {sender}.</p><p>I appreciate your inquiry about '{subject}'. Let's schedule a call to discuss your needs further.</p><p>Best regards,<br>Sales Team</p>",
                'confidence': 0.90,
                'llm_provider_id': provider_id,
                'llm_model': 'simulated-model'
            }
        else:
            return {
                'subject': f"Re: {subject}",
                'body_text': f"Thank you for your message regarding '{subject}'.\n\nWe've received your email and will respond shortly.\n\nBest regards,\nThe Team",
                'body_html': f"<p>Thank you for your message regarding '{subject}'.</p><p>We've received your email and will respond shortly.</p><p>Best regards,<br>The Team</p>",
                'confidence': 0.80,
                'llm_provider_id': provider_id,
                'llm_model': 'simulated-model'
            }

    def analyze_email_content(self, email_data):
        """
        Analyze email content using LLM.
        In production, replace this function with an actual LLM API call.
        """
        provider = self._get_llm_provider()
        provider_id = provider['provider_id'] if provider else None
        
        # Simulate analysis results
        subject = email_data.get('subject', '')
        body = email_data.get('body_text', '')
        
        # Simple heuristics for demonstration
        urgency = 5  # default medium urgency
        if any(word in subject.lower() for word in ['urgent', 'immediate', 'asap', 'emergency']):
            urgency = 9
        elif any(word in subject.lower() for word in ['question', 'inquiry', 'help']):
            urgency = 6
        
        # Determine categories
        categories = []
        if any(word in subject.lower() or word in body.lower() for word in ['price', 'cost', 'quote', 'pricing']):
            categories.append('pricing')
        if any(word in subject.lower() or word in body.lower() for word in ['account', 'login', 'password', 'access']):
            categories.append('account')
        if any(word in subject.lower() or word in body.lower() for word in ['error', 'bug', 'issue', 'problem', 'not working']):
            categories.append('technical_issue')
        
        # Default to general inquiry if no categories detected
        if not categories:
            categories.append('general_inquiry')
        
        # Detect sentiment (very basic implementation)
        positive_words = ['thank', 'great', 'good', 'love', 'excellent', 'appreciate']
        negative_words = ['bad', 'poor', 'issue', 'problem', 'disappointed', 'unhappy', 'refund']
        
        positive_count = sum(1 for word in positive_words if word in body.lower())
        negative_count = sum(1 for word in negative_words if word in body.lower())
        
        if positive_count > negative_count:
            sentiment = 'positive'
        elif negative_count > positive_count:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        # Simple PII detection (very basic)
        contains_pii = False
        if any(pattern in body.lower() for pattern in ['ssn', 'social security', 'credit card', 'passport']):
            contains_pii = True
        
        return {
            'email_id': email_data.get('email_id'),
            'categories': categories,
            'sentiment': sentiment,
            'intent': categories[0],  # Simplification, use primary category as intent
            'urgency': urgency,
            'required_info': [],  # Would be determined by more sophisticated analysis
            'contains_pii': contains_pii,
            'summary': f"Subject: {subject}",  # Simple summary
            'llm_provider_id': provider_id,
            'llm_model': 'simulated-model',
            'confidence': 0.75
        }

    def store_email_in_db(self, email_data, mailbox_type):
        """Store email data in PostgreSQL database"""
        try:
            # Generate UUID for the email
            email_id = str(uuid.uuid4())
            email_data['email_id'] = email_id
            email_data['mailbox_type'] = mailbox_type
            
            # Start a transaction
            cursor = self.db_conn.cursor()
            
            # Insert into emails table
            cursor.execute("""
                INSERT INTO emails (
                    email_id, external_id, thread_id, from_address, from_name, 
                    to_address, cc_addresses, bcc_addresses, subject, body_text, 
                    body_html, received_timestamp, is_read, status, mailbox_type,
                    priority, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING email_id
            """, (
                email_id, 
                email_data.get('external_id'), 
                email_data.get('thread_id'),
                email_data.get('from_address'), 
                email_data.get('from_name'),
                email_data.get('to_address'),
                email_data.get('cc_addresses'),
                email_data.get('bcc_addresses'),
                email_data.get('subject'),
                email_data.get('body_text'),
                email_data.get('body_html'),
                email_data.get('received_timestamp'),
                email_data.get('is_read', False),
                email_data.get('status', 'pending_review'),
                mailbox_type,
                email_data.get('priority', 'normal'),
                Json(email_data.get('metadata', {}))
            ))
            
            # Process attachments if any
            for attachment in email_data.get('attachments', []):
                cursor.execute("""
                    INSERT INTO attachments (
                        email_id, filename, content_type, size, storage_path
                    ) VALUES (%s, %s, %s, %s, %s)
                """, (
                    email_id,
                    attachment.get('filename'),
                    attachment.get('content_type'),
                    attachment.get('size'),
                    attachment.get('storage_path', '')
                ))
            
            # Generate draft reply
            llm_response = self.simulate_llm_response(email_data, mailbox_type)
            
            # Store draft reply
            cursor.execute("""
                INSERT INTO draft_replies (
                    email_id, subject, body_text, body_html, confidence, 
                    llm_provider_id, llm_model
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING draft_id
            """, (
                email_id,
                llm_response.get('subject'),
                llm_response.get('body_text'),
                llm_response.get('body_html', ''),
                llm_response.get('confidence'),
                llm_response.get('llm_provider_id'),
                llm_response.get('llm_model')
            ))
            
            # Store email analysis
            analysis = self.analyze_email_content(email_data)
            
            cursor.execute("""
                INSERT INTO email_analysis (
                    email_id, categories, sentiment, intent, urgency,
                    contains_pii, summary, llm_provider_id, llm_model, confidence
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                email_id,
                analysis.get('categories'),
                analysis.get('sentiment'),
                analysis.get('intent'),
                analysis.get('urgency'),
                analysis.get('contains_pii'),
                analysis.get('summary'),
                analysis.get('llm_provider_id'),
                analysis.get('llm_model'),
                analysis.get('confidence')
            ))
            
            # Commit the transaction
            self.db_conn.commit()
            cursor.close()
            
            logger.info(f"Successfully stored email with ID: {email_id}")
            return email_id
            
        except Exception as e:
            # Rollback in case of error
            self.db_conn.rollback()
            logger.error(f"Error storing email in database: {e}")
            raise

    def process_email_file(self, file_path):
        """Process a single email file"""
        try:
            with open(file_path, 'rb') as f:
                raw_email = f.read()
            
            # Parse the email and extract content
            email_data = self.extract_email_content(raw_email)
            
            # Check if this is for a valid mailbox
            is_valid, mailbox_type = self.is_valid_mailbox(email_data.get('to_address', ''))
            if not is_valid:
                logger.warning(f"Email sent to non-configured mailbox: {email_data.get('to_address', '')}")
                email_data['status'] = 'ignored'
                email_data['notes'] = 'Email sent to non-configured mailbox'
                mailbox_type = 'unconfigured'
            
            # Store the email data in database
            email_id = self.store_email_in_db(email_data, mailbox_type)
            
            return {
                'email_id': email_id,
                'status': 'processed',
                'mailbox_type': mailbox_type
            }
            
        except Exception as e:
            logger.error(f"Error processing email file {file_path}: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }

    def process_emails_from_directory(self, directory):
        """Process all email files in a directory"""
        results = {
            'processed': 0,
            'errors': 0,
            'details': []
        }
        
        for filename in os.listdir(directory):
            if filename.endswith('.eml'):
                file_path = os.path.join(directory, filename)
                try:
                    result = self.process_email_file(file_path)
                    results['details'].append({
                        'file': filename,
                        'result': result
                    })
                    
                    if result.get('status') == 'processed':
                        results['processed'] += 1
                    else:
                        results['errors'] += 1
                        
                except Exception as e:
                    results['errors'] += 1
                    results['details'].append({
                        'file': filename,
                        'result': {
                            'status': 'error',
                            'error': str(e)
                        }
                    })
        
        return results

    def cleanup(self):
        """Close database connection and any other cleanup needed"""
        if hasattr(self, 'db_conn') and self.db_conn:
            self.db_conn.close()

def main():
    parser = argparse.ArgumentParser(description='Process email files and store in database')
    parser.add_argument('--config', help='Path to configuration file')
    parser.add_argument('--db-connection', help='Database connection string')
    parser.add_argument('--input', required=True, help='Input email file or directory')
    parser.add_argument('--mode', choices=['file', 'directory'], default='file', help='Processing mode')
    
    args = parser.parse_args()
    
    processor = EmailProcessor(args.config, args.db_connection)
    
    try:
        if args.mode == 'file':
            result = processor.process_email_file(args.input)
            print(json.dumps(result, indent=2))
        else:
            results = processor.process_emails_from_directory(args.input)
            print(json.dumps(results, indent=2))
    finally:
        processor.cleanup()

if __name__ == "__main__":
    main()
