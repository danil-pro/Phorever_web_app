import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

CLIENT_SECRETS_FILE = os.environ.get('CLIENT_SECRETS_FILE')
SCOPES = os.environ.get('SCOPES')
API_SERVICE_NAME = os.environ.get('API_SERVICE_NAME')
API_VERSION = os.environ.get('API_VERSION')
APP_KEY = os.environ.get('APP_KEY')
APP_SECRET = os.environ.get('APP_SECRET')
DROPBOX_REDIRECT_URI = os.environ.get('DROPBOX_REDIRECT_URI')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI')
SECRET_KEY = os.environ.get('SECRET_KEY')
