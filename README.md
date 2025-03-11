
# Process a single email file
python email_processor.py --config config.json --db-connection "postgres://user:pass@localhost:5432/email_assistant" --input example.eml --mode file

# Process all emails in a directory
python email_processor.py --config config.json --db-connection "postgres://user:pass@localhost:5432/email_assistant" --input ./email_directory --mode directory
