import os

import flask
from flask import *

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from dropbox.exceptions import AuthError
import dropbox
from dropbox import files, sharing

import config
from Oauth2_Connector import GoogleOauth2Connect, DropboxOauth2Connect


CLIENT_SECRETS_FILE = config.CLIENT_SECRETS_FILE

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

SCOPES = [config.SCOPES]
API_SERVICE_NAME = config.API_SERVICE_NAME
API_VERSION = config.API_VERSION
app = flask.Flask(__name__)
app.secret_key = config.SECRET_KEY
GOOGLE_REDIRECT_URI = config.GOOGLE_REDIRECT_URI
google_auth = GoogleOauth2Connect(CLIENT_SECRETS_FILE, SCOPES, API_SERVICE_NAME, API_VERSION)

authenticator = DropboxOauth2Connect(
    app_key=config.APP_KEY,
    app_secret=config.APP_SECRET,
    redirect_uri=config.DROPBOX_REDIRECT_URI,
    session=session
)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/google_authorize')
def google_authorize():
    flow = Flow.from_client_secrets_file(
        google_auth.client_secret_file,
        scopes=google_auth.scopes,
        redirect_uri=GOOGLE_REDIRECT_URI
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    session['state'] = state
    return redirect(authorization_url)


@app.route('/google_oauth2callback')
def google_oauth2callback():
    state = session['state']
    credentials = google_auth.build_credentials(request.url)
    session['credentials'] = google_auth.credentials_to_dict(credentials)
    return redirect(url_for('google_photos'))


@app.route('/google_photos')
def google_photos():
    if 'credentials' not in session:
        return redirect(url_for('google_authorize'))
    credentials = Credentials.from_authorized_user_info(session['credentials'])
    base_url = google_auth.photos(credentials)
    return render_template('img.html', base_url=base_url)


@app.route('/revoke')
def revoke():
    if 'credentials' not in session:
        return ('You need to <a href="/authorize">authorize</a> before ' +
                'testing the code to revoke credentials')
    credentials = Credentials.from_authorized_user_info(session['credentials'])
    revoke = credentials.revoke(Request())
    status_code = revoke.status_code
    if status_code == 200:
        return 'Credentials successfully revoked.'
    else:
        return 'An error occurred.'


@app.route('/clear_google_credentials')
def clear_google_credentials():
    if 'credentials' in session:
        del session['credentials']
    return redirect(url_for('index'))


@app.route('/dropbox_authorize')
def dropbox_authorize():
    if 'access_token' not in session:
        authorize_url = authenticator.start_auth()
        return flask.redirect(authorize_url)
    return redirect(url_for('dropbox_photos'))


@app.route('/dropbox_oauth2callback')
def dropbox_oauth2callback():
    try:
        session['access_token'], session['user_id'] = authenticator.finish_auth(request.args)

    except AuthError as e:
        print(e)
        return redirect(url_for('dropbox_authorize'))
    return redirect(url_for('dropbox_photos'))


@app.route('/dropbox_photos')
def dropbox_photos():
    if 'access_token' not in session:
        authorize_url = authenticator.start_auth()
        return flask.redirect(authorize_url)
    try:
        dbx = dropbox.Dropbox(session['access_token'])

        result = dbx.files_list_folder("", recursive=True)
        base_url = []
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FileMetadata) and entry.name.lower().endswith(('.png', '.jpg', '.jpeg',
                                                                                              '.gif', '.bmp')):
                try:
                    shared_links = dbx.sharing_list_shared_links(entry.id)
                    if len(shared_links.links) > 0:
                        preview_url = shared_links.links[0].url.replace("?dl=0", "?raw=1")
                        print(preview_url)
                    else:
                        settings = dropbox.sharing.SharedLinkSettings(
                            requested_visibility=dropbox.sharing.RequestedVisibility.public)

                        shared_link = dbx.sharing_create_shared_link_with_settings(entry.id, settings)

                        preview_url = shared_link.url.replace("?dl=0", "?raw=1")
                        print(preview_url)
                except Exception as e:
                    preview_url = None
                    print(e)
                if preview_url:
                    base_url.append(preview_url)
                if len(base_url) > 10:
                    break

        return render_template('img.html', base_url=base_url)

    except AuthError as e:
        print(e)


@app.route('/clear_dropbox_credentials')
def clear_dropbox_credentials():
    if 'access_token' in session:
        del session['access_token']
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run()
