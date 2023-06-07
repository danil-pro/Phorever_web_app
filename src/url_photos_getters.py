import os

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
from model import db, Photos, Users, PhotosMetaData
from Worker import Worker

# import requests
import aiohttp
import json

# from concurrent.futures import ThreadPoolExecutor
# import asyncio

photos = Blueprint('photos', __name__, template_folder='../templates', static_folder='../static')
current_dir = os.path.dirname(os.path.abspath(__file__))

CLIENT_SECRETS_FILE = CLIENT_SECRETS_FILE

absolute_path = os.path.join(current_dir, CLIENT_SECRETS_FILE)
print(absolute_path)
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
                photo = Photos(photos_data=photo_data, service=source_function, token=session['credentials']['token'],
                               refresh_token=session['credentials']['refresh_token'], user_id=current_user.id)
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
        current_user_family = Users.query.filter_by(parent_id=current_user.parent_id).all()
        photo_url = []

        for family_user in current_user_family:
            family_user_photos = Photos.query.filter_by(user_id=family_user.id).all()
            correct_family_user_photos = []
            for photo in family_user_photos:
                photos_meta_data = PhotosMetaData.query.filter_by(photo_id=photo.id).first()
                if not photos_meta_data:
                    correct_family_user_photos.append(photo)
            photo_urls = worker.get_photos_from_db(correct_family_user_photos, session['credentials'])
            dict_photo_data = {family_user.email: photo_urls}
            photo_url.append(dict_photo_data)
        return render_template('user_photo.html', photos=photo_url, parent_id=current_user.parent_id)
    else:
        return redirect(url_for('auth.login'))


@photos.route('/add_photo_description/<photo_id>', methods=['GET', 'POST'])
def add_photo_description(photo_id):
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('photos.google_authorize'))

        if request.method == "POST":
            title = request.form['title']
            description = request.form['description']
            location = request.form['location']
            creation_data = request.form['creation_date']

            photo_meta_data = PhotosMetaData.query.filter_by(photo_id=photo_id).first()

            if not photo_meta_data:
                new_photo_meta_data = PhotosMetaData(title=title, description=description,
                                                     location=location, creation_data=creation_data,
                                                     photo_id=photo_id)
                db.session.add(new_photo_meta_data)
                db.session.commit()
                flash('Photo add to tree successful')
            else:
                if title:
                    photo_meta_data.title = title
                if description:
                    photo_meta_data.description = description
                if location:
                    photo_meta_data.location = location
                if creation_data:
                    photo_meta_data.creation_data = creation_data

                db.session.commit()
                flash('Update successful')
            return redirect(url_for('photos.photos_tree'))

    else:
        return redirect(url_for('auth.login'))


@photos.route('/photos_tree', methods=['GET', 'POST'])
def photos_tree():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('photos.google_authorize'))
        current_user_family = Users.query.filter_by(parent_id=current_user.parent_id).all()
        photo_data = []
        for family_user in current_user_family:
            family_user_photos = Photos.query.filter_by(user_id=family_user.id).all()
            photo_urls = worker.get_photos_from_db(family_user_photos, session['credentials'])
            for photo_id, url in photo_urls.items():
                photos_meta_data = PhotosMetaData.query.filter_by(photo_id=photo_id).first()
                if photos_meta_data:
                    photo_data.append({photo_id: {'baseUrl': url,
                                                  'title': photos_meta_data.title,
                                                  'description': photos_meta_data.description,
                                                  'location': photos_meta_data.location,
                                                  'creation_data': photos_meta_data.creation_data}})
            return render_template('photos_tree.html', photo_data=photo_data)
    else:
        return redirect(url_for('auth.login'))
