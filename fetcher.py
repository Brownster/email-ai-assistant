import imaplib
import email
import os
import json
import time
import logging
import datetime
import tempfile
from email import policy
from email.parser import BytesParser
import psycopg2
from psycopg2.extras import Json, DictCursor
import schedule
import threading
import queue
import base64
import quopri
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EmailFetcher:
    def __init__(self, config_path=None, db_connection_string=None, processor=None):
        self.config = self._load_config(config_path) if config_path else {}
        self.fetch_interval = self.config.get('fetch_interval', 300)  # 5 minutes default
        self.email_age_limit = self.config.get('email_age_limit', 24)  # Hours
        self.batch_size = self.config.get('batch_size', 10)
        
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
        
        # Store reference to EmailProcessor if provided
        self.processor = processor
        
        # Set up threading for background fetching
        self.stop_event = threading.Event()
        self.email_queue = queue.Queue()
        self.fetch_thread = None
        self.process_thread = None
    
    def _load_config(self, config_path):
        """Load configuration from a JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}
    
    def get_email_providers(self):
        """Get all active email providers from database"""
        try:
            cursor = self.db_conn.cursor(cursor_factory=DictCursor)
            cursor.execute(
                "SELECT provider_id, name, provider_type, config FROM email_providers WHERE is_active = TRUE"
            )
            providers = cursor.fetchall()
            cursor.close()
            return providers
        except Exception as e:
            logger.error(f"Error getting email providers: {e}")
            return []
    
    def fetch_emails_from_provider(self, provider):
        """Fetch emails from a specific provider"""
        provider_type = provider['provider_type']
        config = provider['config']
        
        if provider_type.lower() == 'gmail':
            return self._fetch_from_gmail(config, provider['provider_id'])
        elif provider_type.lower() == 'outlook':
            return self._fetch_from_outlook(config, provider['provider_id'])
        elif provider_type.lower() == 'imap':
            return self._fetch_from_imap(config, provider['provider_id'])
        else:
            logger.warning(f"Unsupported provider type: {provider_type}")
            return []
    
    def _fetch_from_gmail(self, config, provider_id):
        """Fetch emails from Gmail using IMAP"""
        return self._fetch_from_imap({
            'server': 'imap.gmail.com',
            'port': 993,
            'username': config.get('username'),
            'password': config.get('password'),
            'use_ssl': True,
            'folder': config.get('folder', 'INBOX')
        }, provider_id)
    
    def _fetch_from_outlook(self, config, provider_id):
        """Fetch emails from Outlook using IMAP"""
        return self._fetch_from_imap({
            'server': 'outlook.office365.com',
            'port': 993,
            'username': config.get('username'),
            'password': config.get('password'),
            'use_ssl': True,
            'folder': config.get('folder', 'INBOX')
        }, provider_id)
    
    def _fetch_from_imap(self, config, provider_id):
        """Fetch emails from an IMAP server"""
        server = config.get('server')
        port = config.get('port', 993)
        username = config.get('username')
        password = config.get('password')
        use_ssl = config.get('use_ssl', True)
        folder = config.get('folder', 'INBOX')
        
        # Calculate the date threshold for fetching emails
        date_threshold = (datetime.datetime.now() - 
                          datetime.timedelta(hours=self.email_age_limit)).strftime("%d-%b-%Y")
        
        fetched_emails = []
        
        try:
            # Connect to the IMAP server
            if use_ssl:
                mail = imaplib.IMAP4_SSL(server, port)
            else:
                mail = imaplib.IMAP4(server, port)
            
            # Login
            mail.login(username, password)
            
            # Select the mailbox/folder
            mail.select(folder)
            
            # Search for unread emails newer than the threshold date
            status, messages = mail.search(None, f'(UNSEEN SINCE {date_threshold})')
            
            if status != 'OK':
                logger.error(f"Error searching for emails: {status}")
                mail.logout()
                return []
            
            # Get message IDs
            message_ids = messages[0].split()
            
            # Limit to batch size
            message_ids = message_ids[:self.batch_size]
            
            # Fetch emails
            for msg_id in message_ids:
                try:
                    status, data = mail.fetch(msg_id, '(RFC822)')
                    
                    if status != 'OK':
                        logger.error(f"Error fetching email {msg_id}: {status}")
                        continue
                    
                    # Create a temporary file to store the email
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.eml') as temp_file:
                        temp_file.write(data[0][1])
                        temp_path = temp_file.name
                    
                    fetched_emails.append({
                        'temp_file_path': temp_path,
                        'message_id': msg_id.decode('utf-8'),
                        'provider_id': provider_id
                    })
                    
                    # Mark the email as seen (optional, can be configured)
                    if self.config.get('mark_as_read', True):
                        mail.store(msg_id, '+FLAGS', '\\Seen')
                    
                except Exception as e:
                    logger.error(f"Error processing email {msg_id}: {e}")
            
            # Close connection
            mail.close()
            mail.logout()
            
        except Exception as e:
            logger.error(f"Error connecting to IMAP server {server}: {e}")
        
        return fetched_emails
    
    def process_fetched_email(self, email_info):
        """Process a fetched email using the EmailProcessor"""
        try:
            # Get the temporary file path
            temp_file_path = email_info['temp_file_path']
            
            # Process the email if processor is provided
            if self.processor:
                result = self.processor.process_email_file(temp_file_path)
                
                # Update the email record with provider information
                if result.get('status') == 'processed' and 'email_id' in result:
                    cursor = self.db_conn.cursor()
                    cursor.execute(
                        "UPDATE emails SET provider_id = %s WHERE email_id = %s",
                        (email_info['provider_id'], result['email_id'])
                    )
                    self.db_conn.commit()
                    cursor.close()
                
                # Clean up temporary file
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file {temp_file_path}: {e}")
                
                return result
            else:
                logger.warning("No EmailProcessor provided, cannot process email")
                return {'status': 'error', 'error': 'No processor available'}
        
        except Exception as e:
            logger.error(f"Error processing fetched email: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def fetch_all_emails(self):
        """Fetch emails from all configured providers"""
        providers = self.get_email_providers()
        all_emails = []
        
        for provider in providers:
            try:
                logger.info(f"Fetching emails from provider: {provider['name']}")
                emails = self.fetch_emails_from_provider(provider)
                logger.info(f"Fetched {len(emails)} emails from provider {provider['name']}")
                
                # Add to processing queue
                for email_info in emails:
                    self.email_queue.put(email_info)
                
                all_emails.extend(emails)
            
            except Exception as e:
                logger.error(f"Error fetching from provider {provider['name']}: {e}")
        
        return len(all_emails)
    
    def _fetch_worker(self):
        """Background worker function for fetching emails"""
        logger.info("Email fetch worker started")
        
        while not self.stop_event.is_set():
            try:
                self.fetch_all_emails()
            except Exception as e:
                logger.error(f"Error in fetch worker: {e}")
            
            # Sleep until next scheduled run
            time.sleep(self.fetch_interval)
    
    def _process_worker(self):
        """Background worker function for processing emails"""
        logger.info("Email processing worker started")
        
        while not self.stop_event.is_set():
            try:
                # Get email from queue with timeout
                try:
                    email_info = self.email_queue.get(timeout=10)
                    self.process_fetched_email(email_info)
                    self.email_queue.task_done()
                except queue.Empty:
                    # No emails in queue, continue waiting
                    pass
            except Exception as e:
                logger.error(f"Error in process worker: {e}")
    
    def start_background_fetching(self):
        """Start background email fetching"""
        if self.fetch_thread is not None and self.fetch_thread.is_alive():
            logger.warning("Fetch thread is already running")
            return False
        
        self.stop_event.clear()
        
        # Start fetch thread
        self.fetch_thread = threading.Thread(target=self._fetch_worker)
        self.fetch_thread.daemon = True
        self.fetch_thread.start()
        
        # Start process thread
        self.process_thread = threading.Thread(target=self._process_worker)
        self.process_thread.daemon = True
        self.process_thread.start()
        
        logger.info("Background email fetching started")
        return True
    
    def stop_background_fetching(self):
        """Stop background email fetching"""
        self.stop_event.set()
        
        if self.fetch_thread:
            self.fetch_thread.join(timeout=30)
        
        if self.process_thread:
            self.process_thread.join(timeout=30)
        
        logger.info("Background email fetching stopped")
        return True
    
    def start_scheduled_fetching(self):
        """Start scheduled email fetching using the schedule library"""
        interval_minutes = self.fetch_interval // 60
        
        # Ensure at least 1 minute interval
        if interval_minutes < 1:
            interval_minutes = 1
        
        schedule.every(interval_minutes).minutes.do(self.fetch_all_emails)
        
        # Start the scheduler in a background thread
        scheduler_thread = threading.Thread(target=self._run_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        
        logger.info(f"Scheduled email fetching started (every {interval_minutes} minutes)")
        return True
    
    def _run_scheduler(self):
        """Run the scheduler in a loop"""
        self.stop_event.clear()
        
        while not self.stop_event.is_set():
            schedule.run_pending()
            time.sleep(1)
    
    def cleanup(self):
        """Stop all threads and close connections"""
        self.stop_background_fetching()
        
        if hasattr(self, 'db_conn') and self.db_conn:
            self.db_conn.close()

class EmailProviderFactory:
    """Factory class for creating email provider configurations"""
    
    @staticmethod
    def create_gmail_provider(username, password, name=None, folder='INBOX'):
        """Create a Gmail provider configuration"""
        return {
            'name': name or f"Gmail - {username}",
            'provider_type': 'gmail',
            'config': {
                'username': username,
                'password': password,
                'folder': folder
            }
        }
    
    @staticmethod
    def create_outlook_provider(username, password, name=None, folder='INBOX'):
        """Create an Outlook provider configuration"""
        return {
            'name': name or f"Outlook - {username}",
            'provider_type': 'outlook',
            'config': {
                'username': username,
                'password': password,
                'folder': folder
            }
        }
    
    @staticmethod
    def create_imap_provider(server, username, password, port=993, use_ssl=True, name=None, folder='INBOX'):
        """Create a generic IMAP provider configuration"""
        return {
            'name': name or f"IMAP - {username}@{server}",
            'provider_type': 'imap',
            'config': {
                'server': server,
                'port': port,
                'username': username,
                'password': password,
                'use_ssl': use_ssl,
                'folder': folder
            }
        }

def setup_email_provider(db_connection, provider_config):
    """Set up an email provider in the database"""
    try:
        conn = psycopg2.connect(db_connection)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO email_providers (name, provider_type, config, is_active)
            VALUES (%s, %s, %s, %s)
            RETURNING provider_id
        """, (
            provider_config['name'],
            provider_config['provider_type'],
            Json(provider_config['config']),
            True
        ))
        
        provider_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        return provider_id
    
    except Exception as e:
        logger.error(f"Error setting up email provider: {e}")
        return None

def main():
    import argparse
    from processor import EmailProcessor  # Import the email processor we created earlier
    
    parser = argparse.ArgumentParser(description='Fetch emails from configured providers')
    parser.add_argument('--config', help='Path to configuration file')
    parser.add_argument('--db-connection', help='Database connection string')
    parser.add_argument('--mode', choices=['once', 'background', 'scheduled'], default='once', 
                        help='Fetch mode: once, background, or scheduled')
    parser.add_argument('--interval', type=int, default=300, 
                        help='Fetch interval in seconds (for background/scheduled modes)')
    parser.add_argument('--setup-provider', action='store_true', 
                        help='Set up a new email provider')
    parser.add_argument('--provider-type', choices=['gmail', 'outlook', 'imap'], 
                        help='Provider type for setup')
    parser.add_argument('--username', help='Email username for provider setup')
    parser.add_argument('--password', help='Email password for provider setup')
    parser.add_argument('--server', help='IMAP server for custom provider setup')
    parser.add_argument('--port', type=int, default=993, help='IMAP port for custom provider setup')
    
    args = parser.parse_args()
    
    # Setup database connection
    db_connection = args.db_connection or os.environ.get("DB_CONNECTION_STRING", 
                                                        "postgresql://postgres:postgres@localhost:5432/email_assistant")
    
    # Setup a new provider if requested
    if args.setup_provider:
        if not args.provider_type or not args.username or not args.password:
            print("Error: provider-type, username, and password are required for provider setup")
            return
        
        if args.provider_type == 'gmail':
            provider_config = EmailProviderFactory.create_gmail_provider(args.username, args.password)
        elif args.provider_type == 'outlook':
            provider_config = EmailProviderFactory.create_outlook_provider(args.username, args.password)
        elif args.provider_type == 'imap':
            if not args.server:
                print("Error: server is required for IMAP provider setup")
                return
            provider_config = EmailProviderFactory.create_imap_provider(
                args.server, args.username, args.password, args.port
            )
        
        provider_id = setup_email_provider(db_connection, provider_config)
        if provider_id:
            print(f"Successfully set up email provider with ID: {provider_id}")
        else:
            print("Failed to set up email provider")
        
        return
    
    # Create email processor if not in setup mode
    processor = EmailProcessor(args.config, db_connection)
    
    # Create and configure the fetcher
    fetcher = EmailFetcher(args.config, db_connection, processor)
    
    # Update fetch interval if provided
    if args.interval:
        fetcher.fetch_interval = args.interval
    
    try:
        if args.mode == 'once':
            print("Fetching emails...")
            count = fetcher.fetch_all_emails()
            print(f"Fetched {count} emails")
            
            # Process all emails in the queue
            while not fetcher.email_queue.empty():
                email_info = fetcher.email_queue.get()
                fetcher.process_fetched_email(email_info)
                fetcher.email_queue.task_done()
            
        elif args.mode == 'background':
            print("Starting background email fetching...")
            fetcher.start_background_fetching()
            
            # Keep the main thread running
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("Stopping background fetching...")
                fetcher.stop_background_fetching()
        
        elif args.mode == 'scheduled':
            print(f"Starting scheduled email fetching (every {args.interval//60} minutes)...")
            fetcher.start_scheduled_fetching()
            
            # Keep the main thread running
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("Stopping scheduled fetching...")
                fetcher.stop_background_fetching()
    
    finally:
        # Clean up resources
        fetcher.cleanup()
        processor.cleanup()

if __name__ == "__main__":
    main()
