# email-ai-assistant
em-ai-l




-- Users table (for system users/agents)
CREATE TABLE users (
  user_id SERIAL PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  name VARCHAR(255) NOT NULL,
  role VARCHAR(50) NOT NULL,
  department VARCHAR(50),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Departments table
CREATE TABLE departments (
  department_id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  email_alias VARCHAR(255),
  description TEXT
);

-- Email providers configuration
CREATE TABLE email_providers (
  provider_id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  provider_type VARCHAR(50) NOT NULL, -- 'gmail', 'outlook', etc.
  config JSONB NOT NULL, -- Store configuration as JSON (credentials, endpoints, etc.)
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- LLM providers configuration
CREATE TABLE llm_providers (
  provider_id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  provider_type VARCHAR(50) NOT NULL, -- 'openai', 'anthropic', 'gemini', etc.
  config JSONB NOT NULL, -- Store configuration as JSON (API keys, models, etc.)
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Main emails table
CREATE TABLE emails (
  email_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id VARCHAR(255), -- ID from email provider if applicable
  conversation_id UUID, -- For grouping related emails
  thread_id VARCHAR(255), -- Email thread ID from provider
  from_address VARCHAR(255) NOT NULL,
  from_name VARCHAR(255),
  to_address VARCHAR(255) NOT NULL,
  cc_addresses TEXT[],
  bcc_addresses TEXT[],
  subject VARCHAR(255) NOT NULL,
  body_text TEXT,
  body_html TEXT,
  received_timestamp TIMESTAMP NOT NULL,
  is_read BOOLEAN DEFAULT false,
  status VARCHAR(50) NOT NULL, -- 'pending_review', 'in_progress', 'sent', 'resolved', etc.
  mailbox_type VARCHAR(50) NOT NULL, -- 'support', 'sales', etc.
  department_id INTEGER REFERENCES departments(department_id),
  priority VARCHAR(20) DEFAULT 'normal', -- 'high', 'normal', 'low'
  assigned_to INTEGER REFERENCES users(user_id),
  provider_id INTEGER REFERENCES email_providers(provider_id),
  metadata JSONB, -- Additional metadata from email
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Email attachments
CREATE TABLE attachments (
  attachment_id SERIAL PRIMARY KEY,
  email_id UUID REFERENCES emails(email_id),
  filename VARCHAR(255) NOT NULL,
  content_type VARCHAR(100) NOT NULL,
  size INTEGER NOT NULL,
  storage_path VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Draft replies created by LLM
CREATE TABLE draft_replies (
  draft_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_id UUID REFERENCES emails(email_id),
  subject VARCHAR(255) NOT NULL,
  body_text TEXT NOT NULL,
  body_html TEXT,
  confidence FLOAT,
  llm_provider_id INTEGER REFERENCES llm_providers(provider_id),
  llm_model VARCHAR(100),
  prompt_used TEXT,
  metadata JSONB, -- Additional LLM metadata
  is_edited BOOLEAN DEFAULT false,
  edited_by INTEGER REFERENCES users(user_id),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Email categorization and analysis by LLM
CREATE TABLE email_analysis (
  analysis_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_id UUID REFERENCES emails(email_id),
  categories TEXT[],
  sentiment VARCHAR(50),
  intent VARCHAR(100),
  urgency INTEGER, -- Scale of 1-10
  required_info TEXT[], -- Information needed to complete request
  contains_pii BOOLEAN DEFAULT false,
  summary TEXT,
  llm_provider_id INTEGER REFERENCES llm_providers(provider_id),
  llm_model VARCHAR(100),
  confidence FLOAT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Email activity logs
CREATE TABLE email_activity_logs (
  log_id SERIAL PRIMARY KEY,
  email_id UUID REFERENCES emails(email_id),
  user_id INTEGER REFERENCES users(user_id),
  action_type VARCHAR(50) NOT NULL, -- 'status_change', 'reply_sent', 'viewed', etc.
  previous_value TEXT,
  new_value TEXT,
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_emails_status ON emails(status);
CREATE INDEX idx_emails_conversation_id ON emails(conversation_id);
CREATE INDEX idx_emails_mailbox_type ON emails(mailbox_type);
CREATE INDEX idx_emails_received_timestamp ON emails(received_timestamp);
CREATE INDEX idx_draft_replies_email_id ON draft_replies(email_id);
