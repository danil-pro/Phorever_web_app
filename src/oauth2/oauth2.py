import flask
from flask import *
from src.auth.auth import current_user

from google_auth_oauthlib.flow import Flow

from src.app.config import *
from src.oauth2.Oauth2_Connector import GoogleOauth2Connect, DropboxOauth2Connect

oauth2 = Blueprint('oauth2', __name__, template_folder='../templates', static_folder='../static')
current_dir = os.path.dirname(os.path.abspath(__file__))

CLIENT_SECRETS_FILE = CLIENT_SECRETS_FILE

absolute_path = os.path.join(current_dir, CLIENT_SECRETS_FILE)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

SCOPES = [SCOPE1, SCOPE2, SCOPE3]
API_SERVICE_NAME = API_SERVICE_NAME
API_VERSION = API_VERSION
GOOGLE_REDIRECT_URI = GOOGLE_REDIRECT_URI
google_auth = GoogleOauth2Connect(CLIENT_SECRETS_FILE, SCOPES, API_SERVICE_NAME, API_VERSION)

authenticator = DropboxOauth2Connect(
    app_key=APP_KEY,
    app_secret=APP_SECRET,
    redirect_uri=DROPBOX_REDIRECT_URI,
    session=session
)


@oauth2.route('/google_authorize')
def google_authorize():
    flow = Flow.from_client_secrets_file(
        google_auth.client_secret_file,
        scopes=google_auth.scopes,
        redirect_uri=GOOGLE_REDIRECT_URI
    )
    authorization_url, state = flow.authorization_url(
        prompt='consent',
        access_type='offline',
        include_granted_scopes='true'
    )
    session['state'] = state
    return redirect(authorization_url)


@oauth2.route('/google_oauth2callback')
def google_oauth2callback():
    try:
        state = session['state']
        credentials = google_auth.build_credentials(request.url)
        session['credentials'] = google_auth.credentials_to_dict(credentials)

        return redirect(url_for('user_photos'))
    except Exception as e:
        print(e)
        return redirect(url_for('index'))


@oauth2.route('/google_logout', methods=['GET'])
def google_logout():
    if current_user.is_authenticated:
        if 'credentials' in session:
            del session['credentials']
            return flask.redirect(url_for('oauth2.google_authorize'))
    return redirect(url_for('auth.login'))


@oauth2.route('/dropbox_authorize')
def dropbox_authorize():
    if 'access_token' not in session:
        authorize_url = authenticator.start_auth()
        return flask.redirect(authorize_url)
    return redirect(url_for('photos.dropbox_photos'))


@oauth2.route('/dropbox_oauth2callback')
def dropbox_oauth2callback():
    try:
        session['access_token'], session['user_id'] = authenticator.finish_auth(request.args)
        print(session)
    except Exception as e:
        print(e)
        return redirect(url_for('index'))
    return redirect(url_for('photos.dropbox_photos'))


@oauth2.route('/dropbox_logout')
def dropbox_logout():
    if current_user.is_authenticated:
        if 'access_token' in session:
            del session['access_token'], session['user_id']
            print(session)
            session.modified = True
            authorize_url = authenticator.start_auth()
            return flask.redirect(authorize_url)
    return redirect(url_for('auth.login'))
