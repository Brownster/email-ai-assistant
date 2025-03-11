
# Process a single email file
python email_processor.py --config config.json --db-connection "postgres://user:pass@localhost:5432/email_assistant" --input example.eml --mode file

# Process all emails in a directory
python email_processor.py --config config.json --db-connection "postgres://user:pass@localhost:5432/email_assistant" --input ./email_directory --mode directory

# One-time fetch from all configured providers
python email_fetcher.py --db-connection "postgres://user:pass@localhost/email_assistant" --mode once

# Start background fetching with 5-minute intervals
python email_fetcher.py --db-connection "postgres://user:pass@localhost/email_assistant" --mode background --interval 300

# Add a new Gmail provider
python email_fetcher.py --db-connection "postgres://user:pass@localhost/email_assistant" --setup-provider --provider-type gmail --username "support@yourcompany.com" --password "your-password"

# Add a custom IMAP provider
python email_fetcher.py --setup-provider --provider-type imap --server "imap.example.com" --username "user" --password "pass"


## Setup test db
psql -U your_username -d your_database -f testdb.sql
