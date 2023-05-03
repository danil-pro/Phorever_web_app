import json
import json
import pickle
# import os

import flask
from flask import *
from auth import current_user

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from dropbox.exceptions import AuthError
import dropbox

from config import *
from Oauth2_Connector import GoogleOauth2Connect, DropboxOauth2Connect

# from concurrent.futures import ThreadPoolExecutor
# import asyncio

photos = Blueprint('photos', __name__, template_folder='../templates', static_folder='../static')

CLIENT_SECRETS_FILE = CLIENT_SECRETS_FILE

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

SCOPES = [SCOPES]
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


@photos.route('/google_authorize')
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


@photos.route('/google_oauth2callback')
def google_oauth2callback():
    state = session['state']
    credentials = google_auth.build_credentials(request.url)
    session['credentials'] = google_auth.credentials_to_dict(credentials)
    return redirect(url_for('photos.google_photos'))


@photos.route('/google_photos', methods=['GET'])
async def google_photos():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('photos.google_authorize'))
        # loop = asyncio.get_running_loop()
        try:
            credentials = Credentials.from_authorized_user_info(session['credentials'])
            base_url = await google_auth.photos(credentials)
            if not base_url:
                flash('No photo', 'info')
                return render_template('img.html')
            return render_template('img.html', base_url=base_url)
        except AuthError as e:
            print(e)
    return redirect(url_for('auth.login'))


@photos.route('/dropbox_authorize')
def dropbox_authorize():
    if 'access_token' not in session:
        authorize_url = authenticator.start_auth()
        return flask.redirect(authorize_url)
    return redirect(url_for('photos.dropbox_photos'))


@photos.route('/dropbox_oauth2callback')
def dropbox_oauth2callback():
    try:
        session['access_token'], session['user_id'] = authenticator.finish_auth(request.args)

    except AuthError as e:
        print(e)
        return redirect(url_for('photos.dropbox_authorize'))
    return redirect(url_for('photos.dropbox_photos'))


@photos.route('/dropbox_photos')
async def dropbox_photos():
    if current_user.is_authenticated:
        if 'access_token' not in session:
            authorize_url = authenticator.start_auth()
            return flask.redirect(authorize_url)
        try:
            dbx = dropbox.Dropbox(session['access_token'])
            base_url = await authenticator.get_all_preview_urls(dbx)
            if not base_url:
                flash('No photo', 'info')
                return render_template('img.html')
            return render_template('img.html', base_url=base_url)
        except AuthError as e:
            print(e)
    return redirect(url_for('auth.login'))
