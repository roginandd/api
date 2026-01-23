import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
import json
import os

load_dotenv()
def initialize_firebase():
    # Check if Firebase is already initialized to prevent errors during hot-reloads
    if not firebase_admin._apps:
        private_key = os.environ.get('FIREBASE_PRIVATE_KEY')
        
        # 3. FIX NEWLINES (Crucial for both .env and Vercel)
        if private_key:
            private_key = private_key.replace('\\n', '\n')

        service_account_info = {
            "type": os.environ.get('FIREBASE_TYPE'),
            "project_id": os.environ.get('FIREBASE_PROJECT_ID'),
            "private_key_id": os.environ.get('FIREBASE_PRIVATE_KEY_ID'),
            "private_key": private_key,
            "client_email": os.environ.get('FIREBASE_CLIENT_EMAIL'),
            "client_id": os.environ.get('FIREBASE_CLIENT_ID'),
            "auth_uri": os.environ.get('FIREBASE_AUTH_URI'),
            "token_uri": os.environ.get('FIREBASE_TOKEN_URI'),
            "auth_provider_x509_cert_url": os.environ.get('FIREBASE_AUTH_PROVIDER_CERT_URL'),
            "client_x509_cert_url": os.environ.get('FIREBASE_CLIENT_CERT_URL'),
            "universe_domain": os.environ.get('FIREBASE_UNIVERSE_DOMAIN')
        }
        # Load the credentials
        cred = credentials.Certificate(service_account_info)
                # Initialize the app
        firebase_admin.initialize_app(cred)

# Initialize it immediately
initialize_firebase()

# Expose the Firestore client
db = firestore.client(database_id='vista-db')