-- Run this script to create and populate a test database for the Email Management Dashboard

-- Create test users
INSERT INTO users (email, name, role, department) VALUES
('john.doe@company.com', 'John Doe', 'Support Agent', 'Customer Support'),
('jane.smith@company.com', 'Jane Smith', 'Support Manager', 'Customer Support'),
('alex.wong@company.com', 'Alex Wong', 'Sales Representative', 'Sales');

-- Create departments
INSERT INTO departments (name, email_alias, description) VALUES
('Customer Support', 'support@company.com', 'Handles customer inquiries and technical issues'),
('Sales', 'sales@company.com', 'Manages product inquiries and sales opportunities'),
('Billing', 'billing@company.com', 'Handles payment and invoice related inquiries');

-- Create email provider
INSERT INTO email_providers (name, provider_type, config, is_active) VALUES
('Company Gmail', 'gmail', '{"client_id": "test_client_id", "client_secret": "test_client_secret", "redirect_uri": "http://localhost:3000/oauth/callback"}', true);

-- Create LLM provider
INSERT INTO llm_providers (name, provider_type, config, is_active) VALUES
('OpenAI GPT-4', 'openai', '{"api_key": "test_api_key", "model": "gpt-4", "temperature": 0.7}', true),
('Anthropic Claude', 'anthropic', '{"api_key": "test_anthropic_key", "model": "claude-3-sonnet-20240229", "temperature": 0.7}', true);

-- Create sample emails
INSERT INTO emails (
  external_id, conversation_id, thread_id, from_address, from_name, 
  to_address, subject, body_text, received_timestamp, is_read, 
  status, mailbox_type, department_id, priority, assigned_to, provider_id
) VALUES
-- Email 1: Pending review
(
  'e_1001', gen_random_uuid(), 'thread_1001', 
  'customer1@example.com', 'Jane Customer', 
  'support@company.com', 
  'Need help with my subscription', 
  'Hello,\n\nI recently upgraded to the premium plan but I don''t see the new features available in my account. Can you please help me resolve this issue?\n\nThanks,\nJane',
  CURRENT_TIMESTAMP - INTERVAL '2 hours', 
  false, 'pending_review', 'support', 1, 'high', null, 1
),
-- Email 2: In progress
(
  'e_1002', gen_random_uuid(), 'thread_1002', 
  'customer2@example.com', 'Bob Smith', 
  'support@company.com', 
  'Error message when trying to save project', 
  'Hi Support Team,\n\nI keep getting an error that says "Unable to save changes" when I try to save my project. This started happening after the latest update. I''ve attached a screenshot of the error.\n\nRegards,\nBob',
  CURRENT_TIMESTAMP - INTERVAL '5 hours', 
  true, 'in_progress', 'support', 1, 'normal', 1, 1
),
-- Email 3: Resolved
(
  'e_1003', gen_random_uuid(), 'thread_1003', 
  'potential_client@example.com', 'Michael Johnson', 
  'sales@company.com', 
  'Interested in enterprise plan pricing', 
  'Hello Sales Team,\n\nI''m looking into your product for my company (123 Corp) with about 200 employees. Could you send me information about your enterprise pricing and features?\n\nBest,\nMichael Johnson\nIT Director, 123 Corp',
  CURRENT_TIMESTAMP - INTERVAL '2 days', 
  true, 'resolved', 'sales', 2, 'high', 3, 1
),
-- Email 4: Sent
(
  'e_1004', gen_random_uuid(), 'thread_1004', 
  'billing_question@example.com', 'Sarah Lee', 
  'billing@company.com', 
  'Question about my recent invoice', 
  'Hi,\n\nI just received invoice #12345 but it shows charges for features I don''t use. I believe there might be an error in my billing. Can you please review this and let me know?\n\nThanks,\nSarah',
  CURRENT_TIMESTAMP - INTERVAL '1 day', 
  true, 'sent', 'billing', 3, 'normal', 2, 1
),
-- Email 5: Pending review (different category)
(
  'e_1005', gen_random_uuid(), 'thread_1005', 
  'technical_question@example.com', 'David Chen', 
  'support@company.com', 
  'API integration documentation', 
  'Hello Support,\n\nI''m trying to integrate your API with our system but I''m having trouble finding complete documentation. Specifically, I need information about the authentication process and rate limits.\n\nCan you point me to the right resources?\n\nRegards,\nDavid',
  CURRENT_TIMESTAMP - INTERVAL '3 hours', 
  false, 'pending_review', 'support', 1, 'normal', null, 1
);

-- Create sample email analysis
INSERT INTO email_analysis (
  email_id, categories, sentiment, intent, urgency, required_info, summary, llm_provider_id, llm_model, confidence
) 
SELECT 
  email_id,
  CASE 
    WHEN mailbox_type = 'support' AND subject LIKE '%subscription%' THEN ARRAY['Account', 'Subscription', 'Billing']
    WHEN mailbox_type = 'support' AND subject LIKE '%Error%' THEN ARRAY['Technical Issue', 'Bug Report']
    WHEN mailbox_type = 'sales' THEN ARRAY['Sales Inquiry', 'Enterprise']
    WHEN mailbox_type = 'billing' THEN ARRAY['Billing Issue', 'Invoice']
    ELSE ARRAY['General Inquiry']
  END,
  CASE 
    WHEN subject LIKE '%Error%' OR subject LIKE '%issue%' THEN 'negative'
    WHEN subject LIKE '%question%' OR subject LIKE '%help%' THEN 'neutral'
    WHEN subject LIKE '%Interested%' THEN 'positive'
    ELSE 'neutral'
  END,
  CASE 
    WHEN subject LIKE '%Error%' OR subject LIKE '%issue%' THEN 'request_support'
    WHEN subject LIKE '%question%' OR subject LIKE '%help%' THEN 'information_request'
    WHEN subject LIKE '%Interested%' THEN 'sales_inquiry'
    ELSE 'general_inquiry'
  END,
  CASE 
    WHEN priority = 'high' THEN 8
    WHEN priority = 'normal' THEN 5
    ELSE 3
  END,
  CASE 
    WHEN mailbox_type = 'support' AND subject LIKE '%subscription%' THEN ARRAY['Account email', 'Subscription plan', 'Date of upgrade']
    WHEN mailbox_type = 'support' AND subject LIKE '%Error%' THEN ARRAY['Software version', 'Steps to reproduce', 'Screenshot of error']
    WHEN mailbox_type = 'sales' THEN ARRAY['Company size', 'Current solutions', 'Budget']
    WHEN mailbox_type = 'billing' THEN ARRAY['Invoice number', 'Account ID']
    ELSE ARRAY['Additional details']
  END,
  CASE 
    WHEN mailbox_type = 'support' AND subject LIKE '%subscription%' THEN 'Customer upgraded to premium but does not see new features. Needs help accessing premium features.'
    WHEN mailbox_type = 'support' AND subject LIKE '%Error%' THEN 'Customer experiencing "Unable to save changes" error after recent update. Included screenshot of the error.'
    WHEN mailbox_type = 'sales' THEN 'IT Director from 123 Corp (200 employees) requesting enterprise pricing and feature information.'
    WHEN mailbox_type = 'billing' THEN 'Customer believes invoice #12345 contains incorrect charges for unused features. Requesting review of the billing.'
    ELSE 'Customer needs assistance with a general inquiry.'
  END,
  1, -- OpenAI GPT-4
  'gpt-4',
  RANDOM()
FROM emails;

-- Create sample draft replies
INSERT INTO draft_replies (
  email_id, subject, body_text, body_html, confidence, llm_provider_id, llm_model, prompt_used
)
SELECT 
  email_id,
  'Re: ' || subject,
  CASE 
    WHEN mailbox_type = 'support' AND subject LIKE '%subscription%' THEN 
      'Hi Jane,

Thank you for reaching out to our support team.

I understand you recently upgraded to the premium plan but are not seeing the new features available in your account. I''d be happy to help you resolve this issue.

Could you please provide the following information so I can better assist you:
1. The email address associated with your account
2. When you completed the upgrade to premium
3. Which specific premium features you are unable to access

In the meantime, I recommend trying the following troubleshooting steps:
- Log out and log back into your account
- Clear your browser cache and cookies
- Try accessing your account from a different browser

Once I have the additional details from you, I''ll be able to investigate further and make sure you have full access to all the premium features you''ve paid for.

Best regards,
The Support Team'

    WHEN mailbox_type = 'support' AND subject LIKE '%Error%' THEN 
      'Hello Bob,

Thank you for reporting this issue with saving your project. I appreciate you providing the screenshot of the error message.

Based on the information you''ve shared, this appears to be related to our recent update. Our technical team is aware of this issue and is working on a fix that will be deployed in the next 24 hours.

In the meantime, you can try the following workaround:
1. Go to Settings > Advanced
2. Toggle off the "Auto-save" feature
3. Save your project manually using Ctrl+S (or Cmd+S on Mac)

This should allow you to save your changes until the permanent fix is deployed. If you continue to experience issues after trying this workaround, please let me know and I''ll escalate this to our development team.

I apologize for the inconvenience this has caused. We''ll notify you as soon as the fix is available.

Regards,
John Doe
Support Team'

    WHEN mailbox_type = 'sales' THEN 
      'Hello Michael,

Thank you for your interest in our enterprise plan for 123 Corp.

I''d be happy to provide you with information about our enterprise pricing and features. For a company of your size (200 employees), our Enterprise Plus plan would likely be the most suitable option.

Key features of our Enterprise Plus plan include:
- Unlimited users and projects
- Priority 24/7 support
- Advanced security features including SSO and SAML
- Custom integrations with your existing systems
- Dedicated account manager
- Quarterly business reviews

Regarding pricing, our Enterprise Plus plan starts at $20 per user per month with annual billing. However, we offer volume discounts for organizations with more than 100 users, which would apply in your case.

I''d like to schedule a call to discuss your specific requirements and provide a tailored quote. Would you be available for a 30-minute call this week? I could also arrange for a product demonstration with one of our solution engineers.

Looking forward to hearing from you.

Best regards,
Alex Wong
Sales Representative'

    WHEN mailbox_type = 'billing' THEN 
      'Hi Sarah,

Thank you for bringing this to our attention regarding invoice #12345.

I''ve reviewed your account and I can see that there appears to be an error in the recent charges. You''re right that there are features listed that aren''t currently activated on your account.

I''ve processed a corrected invoice which you should receive shortly. The new invoice reflects only the features you''re actively using, and I''ve applied a credit to your account for the difference.

Please review the new invoice when you receive it, and let me know if you have any further questions or concerns.

We apologize for the confusion and thank you for your patience while we resolved this issue.

Best regards,
Jane Smith
Billing Support Team'

    ELSE 'Thank you for your email. We will get back to you shortly.'
  END,
  NULL, -- No HTML version for simplicity
  RANDOM() * 0.4 + 0.6, -- Random confidence between 0.6 and 1.0
  CASE 
    WHEN mailbox_type IN ('support', 'billing') THEN 1 -- OpenAI for support and billing
    ELSE 2 -- Anthropic for sales
  END,
  CASE 
    WHEN mailbox_type IN ('support', 'billing') THEN 'gpt-4'
    ELSE 'claude-3-sonnet-20240229'
  END,
  'Generate a helpful and professional response to this customer email'
FROM emails;

-- Create some sample activity logs
INSERT INTO email_activity_logs (
  email_id, user_id, action_type, previous_value, new_value, notes
)
SELECT 
  e.email_id,
  u.user_id,
  CASE 
    WHEN e.status = 'in_progress' THEN 'status_change'
    WHEN e.status = 'resolved' THEN 'status_change'
    WHEN e.status = 'sent' THEN 'reply_sent'
    ELSE 'viewed'
  END,
  CASE 
    WHEN e.status = 'in_progress' THEN 'pending_review'
    WHEN e.status = 'resolved' THEN 'in_progress'
    WHEN e.status = 'sent' THEN NULL
    ELSE NULL
  END,
  e.status,
  CASE 
    WHEN e.status = 'in_progress' THEN 'Assigned to agent for handling'
    WHEN e.status = 'resolved' THEN 'Issue resolved successfully'
    WHEN e.status = 'sent' THEN 'Reply sent to customer'
    ELSE 'Agent viewed the email'
  END
FROM emails e
JOIN users u ON (
  CASE 
    WHEN e.assigned_to IS NOT NULL THEN e.assigned_to = u.user_id
    ELSE u.role = 'Support Agent' -- Default to first support agent
  END
)
WHERE e.status != 'pending_review';
