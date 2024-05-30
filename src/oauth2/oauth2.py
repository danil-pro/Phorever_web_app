import flask
from flask import *
from flask_login import current_user
from flask_restful import Api
from google_auth_oauthlib.flow import Flow

from src.app.config import *
from src.app.model import User, db
from src.oauth2.Oauth2_Connector import GoogleOauth2Connect
from src.photos.DBHandler import DBHandler

oauth2 = Blueprint('oauth2', __name__, template_folder='../templates', static_folder='../static')
current_dir = os.path.dirname(os.path.abspath(__file__))

absolute_path = os.path.abspath(CLIENT_SECRETS_FILE)

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

api = Api()
SCOPES = [SCOPE1, SCOPE2, SCOPE3]
API_SERVICE_NAME = API_SERVICE_NAME
API_VERSION = API_VERSION
GOOGLE_REDIRECT_URI = GOOGLE_REDIRECT_URI
google_auth = GoogleOauth2Connect(CLIENT_SECRETS_FILE, SCOPES, API_SERVICE_NAME, API_VERSION)
db_handler = DBHandler()


@oauth2.route('/google_authorize')
def google_authorize(user_id=None):
    flow = Flow.from_client_secrets_file(
        google_auth.client_secret_file,
        scopes=google_auth.scopes,
        redirect_uri=GOOGLE_REDIRECT_URI
    )
    authorization_url, state = flow.authorization_url(
        prompt='consent',
        access_type='offline',
        include_granted_scopes='true',

    )
    if user_id:
        user = User.query.filter_by(id=user_id).first()
        user.state = state
        db.session.add(user)
        db.session.commit()
        return authorization_url

    else:
        user = User.query.filter_by(id=current_user.id).first()
        user.state = state
        db.session.add(user)
        db.session.commit()
        return redirect(authorization_url)


@oauth2.route('/google_oauth2callback')
def google_oauth2callback():
    try:
        state = request.args.get('state')
        user = User.query.filter_by(state=state).first()
        credentials = google_auth.build_credentials(request.url)
        google_auth.credentials_add_to_db(credentials, user.id)
        if not current_user:
            return {'message': 'ok'}
        else:
            return redirect(url_for('user_photos'))

    except Exception as e:
        print(e)
        return redirect(url_for('auth.login'))


@oauth2.route('/google_logout', methods=['GET'])
def google_logout():
    if current_user.is_authenticated:
        if 'credentials' in session:
            del session['credentials']
            return flask.redirect(url_for('oauth2.google_authorize'))
    return redirect(url_for('auth.login'))


def check_credentials(user_id=None, service='google'):
    user = User.query.filter_by(id=user_id).first()
    if service == 'google':
        with open('GOOGLE_CREDENTIALS.json', 'r') as json_file:
            google_credentials = json.load(json_file)
        if not user:
            if current_user.google_token is None and current_user.google_refresh_token is None:
                return redirect(url_for('oauth2.google_authorize'))
            credentials = {'token': current_user.google_token,
                           'refresh_token': current_user.google_refresh_token,
                           'token_uri': google_credentials['token_uri'],
                           'client_id': google_credentials['client_id'],
                           'client_secret': google_credentials['client_secret'],
                           'scopes': google_credentials['scopes']}
            db_handler.get_photos_from_db(current_user, credentials)
            return credentials
        else:

            credentials = {'token': user.google_token,
                           'refresh_token': user.google_refresh_token,
                           'token_uri': google_credentials['token_uri'],
                           'client_id': google_credentials['client_id'],
                           'client_secret': google_credentials['client_secret'],
                           'scopes': google_credentials['scopes']}
            db_handler.get_photos_from_db(user, credentials)
            return credentials
