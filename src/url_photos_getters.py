# import os

import flask
from flask import *
from auth import current_user

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from dropbox.exceptions import AuthError
import dropbox

from config import *
from Oauth2_Connector import GoogleOauth2Connect, DropboxOauth2Connect
from model import db, Photos, Users
from Worker import Worker

# import requests
import aiohttp
import json

# from concurrent.futures import ThreadPoolExecutor
# import asyncio

photos = Blueprint('photos', __name__, template_folder='../templates', static_folder='../static')

CLIENT_SECRETS_FILE = CLIENT_SECRETS_FILE
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

worker = Worker()


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
    try:
        state = session['state']
        credentials = google_auth.build_credentials(request.url)
        session['credentials'] = google_auth.credentials_to_dict(credentials)
        user = Users.query.filter_by(id=current_user.id).first()
        if not user.refresh_token:
            user.refresh_token = session['credentials'].get('refresh_token')
            user.token = session['credentials'].get('token')
            db.session.add(user)
            db.session.commit()

        return redirect(url_for('photos.user_photos'))
    except Exception as e:
        print(e)
        return redirect(url_for('index'))


@photos.route('/google_photos', methods=['GET'])
def google_photos():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('photos.google_authorize'))
        try:
            credentials = Credentials.from_authorized_user_info(session['credentials'])
            photos_data = google_auth.photos(credentials)
            user_photo_ids = [photo.photos_data for photo in Photos.query.filter().all()
                              if photo.service == '/photos/google_photos']
            if not photos_data:
                flash('No photo', 'info')
                return render_template('img.html', source_function=url_for('photos.google_photos'))
            for user_photo_id in user_photo_ids:
                for data in photos_data:
                    if user_photo_id == data['photoId']:
                        photos_data.remove(data)
            return render_template('img.html', base_url=photos_data,
                                   source_function=url_for('photos.google_photos'))
        except AuthError as e:
            print(e)
    return redirect(url_for('auth.login'))


@photos.route('/add_photo', methods=['GET', 'POST'])
def add_photo():
    if current_user.is_authenticated:
        if request.method == 'POST':
            photos_data = request.form.getlist('selected_photos')
            source_function = request.form.get('source_function')

            for photo_data in photos_data:
                photo = Photos(photos_data=photo_data, service=source_function, user_id=current_user.id)
                db.session.add(photo)
            db.session.commit()
            return redirect(url_for('photos.user_photos'))
    return redirect(url_for('auth.login'))


@photos.route('/google_logout', methods=['GET'])
def google_logout():
    if current_user.is_authenticated:
        if 'credentials' in session:
            del session['credentials']
            return flask.redirect(url_for('photos.google_authorize'))
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
        print(session)
    except Exception as e:
        print(e)
        return redirect(url_for('index'))
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
                return render_template('img.html', source_function=url_for('photos.dropbox_photos'))
            return render_template('img.html', base_url=base_url, source_function=url_for('photos.dropbox_photos'))
        except AuthError as e:
            print(e)
    return redirect(url_for('auth.login'))


@photos.route('/dropbox_logout')
def dropbox_logout():
    if current_user.is_authenticated:
        if 'access_token' in session:
            del session['access_token'], session['user_id']
            print(session)
            session.modified = True
            authorize_url = authenticator.start_auth()
            return flask.redirect(authorize_url)
    return redirect(url_for('auth.login'))


@photos.route('/user_photos', methods=['GET', 'POST'])
def user_photos():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('photos.google_authorize'))
        current_user_photos = Photos.query.filter_by(user_id=current_user.id).all()
        parent_photos = Photos.query.filter_by(user_id=current_user.parent_id).all()
        parent_user = Users.query.filter_by(id=current_user.parent_id).first()
        current_user_family = Users.query.filter_by(parent_id=current_user.parent_id).all()
        user = Users.query.filter_by(id=current_user.id).first()
        photo_url = {}

        for family_user in current_user_family:
            session['credentials']['refresh_token'] = family_user.refresh_token
            session['credentials']['token'] = family_user.token
            print(family_user.id)
            family_user_photos = Photos.query.filter_by(user_id=family_user.id).all()
            photo_urls = worker.get_photos_from_db(family_user_photos, session['credentials'])
            photo_url.setdefault(family_user.email, []).extend(photo_urls)
        #
        # if current_user_photos:
        #     photo_urls = worker.get_photos_from_db(current_user_photos, session['credentials'])
        #     photo_url.setdefault(user.email, []).extend(photo_urls)
        # if parent_user:
        #     if parent_photos:
        #         session['credentials']['refresh_token'] = parent_user.refresh_token
        #         session['credentials']['token'] = parent_user.token
        #         photo_urls = worker.get_photos_from_db(parent_photos, session['credentials'])
        #         photo_url.setdefault(parent_user.email, []).extend(photo_urls)

            session['credentials']['refresh_token'] = user.refresh_token
            session['credentials']['token'] = user.token
        return render_template('user_photo.html', photos=photo_url)
    else:
        return redirect(url_for('auth.login'))
