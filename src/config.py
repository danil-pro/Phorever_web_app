import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

CLIENT_SECRETS_FILE = os.environ.get('CLIENT_SECRETS_FILE')
SCOPE1 = os.environ.get('SCOPE1')
SCOPE2 = os.environ.get('SCOPE2')
SCOPE3 = os.environ.get('SCOPE3')
API_SERVICE_NAME = os.environ.get('API_SERVICE_NAME')
API_VERSION = os.environ.get('API_VERSION')
APP_KEY = os.environ.get('APP_KEY')
APP_SECRET = os.environ.get('APP_SECRET')
DROPBOX_REDIRECT_URI = os.environ.get('DROPBOX_REDIRECT_URI')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI')
SECRET_KEY = os.environ.get('SECRET_KEY')
STMP_SERVER = os.environ.get('STMP_SERVER')
STMP_PORT = os.environ.get('STMP_PORT')
STMP_USERNAME = os.environ.get('STMP_USERNAME')
STMP_PASSWORD = os.environ.get('STMP_PASSWORD')
SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI')
REVOKE_TOKEN = os.environ.get('REVOKE_TOKEN')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
