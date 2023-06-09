import json
import pickle

import flask
from flask import *
from src.auth.auth import current_user

from google.oauth2.credentials import Credentials

from dropbox.exceptions import AuthError
import dropbox
from dropbox import files, sharing

# from src.app.config import *
from src.app.model import db, Photos, Users, PhotosMetaData, EditingPermission, FaceEncode
from src.photos.DBHandler import DBHandler
from src.oauth2.oauth2 import authenticator
from src.app.Forms import UpdateForm, UpdateLocationForm, UpdateCreationDateForm

import asyncio

import src.photos.Get_photos_from_API
import numpy as np
import json
from pyicloud import PyiCloudService
import keyring
from pyicloud.exceptions import PyiCloudNoStoredPasswordAvailableException


photos = Blueprint('photos', __name__, template_folder='../templates/photo_templates', static_folder='../static')

db_handler = DBHandler()

Get_photos_from_API = src.photos.Get_photos_from_API


@photos.route('/google_photos', methods=['GET', 'POST'])
def google_photos():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        try:
            credentials = Credentials.from_authorized_user_info(session['credentials'])

            if request.method == "POST":
                if 'next_page' in request.form:
                    next_page_token = request.form.get('next_page_token')
                    photos_data, next_page_token = Get_photos_from_API.photo_from_google(credentials, next_page_token)
                else:
                    photos_data, next_page_token = Get_photos_from_API.photo_from_google(credentials, None)
            else:
                photos_data, next_page_token = Get_photos_from_API.photo_from_google(credentials, None)

            user_photo_ids = [photo.photos_data for photo in Photos.query.filter().all()
                              if photo.service == '/photos/google_photos']
            if not photos_data:
                flash('No photo', 'info')
                return render_template('photo_templates/img.html', source_function=url_for('photos.google_photos'))
            for user_photo_id in user_photo_ids:
                for data in photos_data:
                    if user_photo_id == data['photoId']:
                        photos_data.remove(data)

            return render_template('photo_templates/img.html', base_url=photos_data,
                                   source_function=url_for('photos.google_photos'),
                                   next_page_token=next_page_token)
        except AuthError as e:
            print(e)
    return redirect(url_for('auth.login'))


@photos.route('/add_photo', methods=['GET', 'POST'])
def add_photo():
    if current_user.is_authenticated:
        if request.method == 'POST':
            photos_data = request.form.getlist('selected_photos')
            source_function = request.form.get('source_function')
            # download_photos = db_handler.download_photos(session['credentials'], photos_data)
            # face_encode_handler = db_handler.face_encode_handler(download_photos)
            for photo_data in photos_data:
                if source_function == '/photos/google_photos':
                    photo = Photos(photos_data=photo_data, service=source_function,
                                   token=session['credentials']['token'],
                                   refresh_token=session['credentials']['refresh_token'],
                                   apple_id=None,
                                   user_id=current_user.id)
                    db.session.add(photo)
                elif source_function == '/photos/icloud_photos':
                    photo = Photos(photos_data=photo_data, service=source_function,
                                   token=None,
                                   refresh_token=None,
                                   apple_id=session['icloud_credentials']['apple_id'],
                                   user_id=current_user.id)
                    db.session.add(photo)
            db.session.commit()
            # for photo_id, face_encode in face_encode_handler.items():
            #     photo = Photos.query.filter_by(photos_data=photo_id).first()
            #     for faces in face_encode:
            #         face = FaceEncode(face_encode=faces,
            #                           photo_id=photo.id, user_id=current_user.id)
            #         db.session.add(face)
            #     db.session.commit()

            return redirect(url_for('user_photos'))
    return redirect(url_for('auth.login'))


@photos.route('/dropbox_photos', methods=['GET', 'POST'])
async def dropbox_photos():
    if current_user.is_authenticated:
        if 'access_token' not in session:
            authorize_url = authenticator.start_auth()
            return flask.redirect(authorize_url)
        try:
            dbx = dropbox.Dropbox(session['access_token'])

            if request.method == 'POST' and 'next_page' in request.form:
                cursor = session['cursor']
                if cursor:
                    files = await asyncio.to_thread(dbx.files_list_folder_continue, cursor)
                else:
                    return redirect(url_for('photos.dropbox_photos'))
            else:
                files = await asyncio.to_thread(dbx.files_list_folder, '', recursive=True, limit=10)

            base_url = []
            for entry in files.entries:
                if isinstance(entry, dropbox.files.FileMetadata) and entry.name.lower().endswith(
                        ('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    shared_links = await asyncio.to_thread(dbx.sharing_list_shared_links, path=entry.path_display)
                    if len(shared_links.links) > 0:
                        preview_url = shared_links.links[0].url.replace("?dl=0", "?raw=1")
                    else:
                        settings = dropbox.sharing.SharedLinkSettings(
                            requested_visibility=dropbox.sharing.RequestedVisibility.public)
                        shared_link = await asyncio.to_thread(dbx.sharing_create_shared_link_with_settings,
                                                              entry.path_display, settings)
                        preview_url = shared_link.url.replace("?dl=0", "?raw=1")
                    if preview_url:
                        base_url.append(preview_url)

            session['cursor'] = files.cursor

            if not files.has_more:
                session['cursor'] = None

            if not base_url:
                flash('No photo', 'info')
                return render_template('photo_templates/img.html', source_function=url_for('photos.dropbox_photos'))

            return render_template('photo_templates/img.html', base_url=base_url,
                                   source_function=url_for('photos.dropbox_photos'))

        except AuthError as e:
            print(e)

    return redirect(url_for('auth.login'))


@photos.route('/icloud_photos', methods=['GET', 'POST'])
def icloud_photos():
    if current_user.is_authenticated:
        if 'icloud_credentials' not in session:
            return redirect(url_for('oauth2.icloud_authorize'))
        try:
            icloud_password = keyring.get_password("pyicloud", session['icloud_credentials']['apple_id'])
            api = PyiCloudService(session['icloud_credentials']['apple_id'], icloud_password)
            photo_ids = set()  # Множество для хранения уникальных идентификаторов фотографий
            data_url = []

            for photo in api.photos.albums['All Photos']:
                for version, data in photo.versions.items():
                    if data['type'] == 'public.jpeg' and photo.id not in photo_ids:
                        data_url.append({photo.id: data['url']})
                        photo_ids.add(photo.id)

            return render_template('photo_templates/img.html', base_url=data_url,
                                   source_function=url_for('photos.icloud_photos'))

        except PyiCloudNoStoredPasswordAvailableException:
            flash('invalid password')
            return redirect(url_for('oauth2.icloud_authorize'))

    return redirect(url_for('auth.login'))


@photos.route('/update_media_meta_data', methods=['GET', 'POST'])
def update_media_meta_data():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        location_form = UpdateLocationForm(request.form)
        creation_date_form = UpdateCreationDateForm(request.form)
        if request.method == "POST":
            if location_form.validate_on_submit() or creation_date_form.validate_on_submit():
                selected_photos = request.form['selected_photos']
                location = request.form['location']
                creation_date = request.form['creation_date']

                if selected_photos:
                    photo_ids = [int(x) for x in selected_photos.split(',')]
                    if location:
                        for photo_id in photo_ids:
                            photo_meta_data = PhotosMetaData.query.filter_by(photo_id=photo_id).first()
                            if not photo_meta_data:
                                new_photo_meta_data = PhotosMetaData(title='Empty title',
                                                                     description='Empty description',
                                                                     location=location_form.location.data,
                                                                     photo_id=photo_id)
                                db.session.add(new_photo_meta_data)
                                db.session.commit()
                            else:
                                photo_meta_data.location = location_form.location.data
                                db.session.add(photo_meta_data)
                        db.session.commit()
                        flash('Update successful')
                    if creation_date:
                        for photo_id in photo_ids:
                            photo_meta_data = PhotosMetaData.query.filter_by(photo_id=photo_id).first()
                            if not photo_meta_data:
                                new_photo_meta_data = PhotosMetaData(title='Empty title',
                                                                     description='Empty description',
                                                                     location='Empty location',
                                                                     creation_data=creation_date_form.creation_date.data,
                                                                     photo_id=photo_id)
                                db.session.add(new_photo_meta_data)
                                db.session.commit()
                            else:
                                photo_meta_data.creation_data = creation_date_form.creation_date.data
                                db.session.add(photo_meta_data)
                        db.session.commit()
                        flash('Update successful')
                return redirect(url_for('user_photos'))

        return redirect(url_for('user_photos'))
    else:
        return redirect(url_for('auth.login'))


@photos.route('/add_photo_description', methods=['GET', 'POST'])
def add_photo_description():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        form = UpdateForm(request.form)
        if request.method == "POST" and form.validate_on_submit():
            description = request.form['description']
            photo_id = request.form['photo_id']

            photo_meta_data = PhotosMetaData.query.filter_by(photo_id=photo_id).first()

            if not photo_meta_data:
                new_photo_meta_data = PhotosMetaData(title=form.title.data, description=description,
                                                     location=form.location.data, creation_data=form.creation_date.data,
                                                     photo_id=photo_id)
                db.session.add(new_photo_meta_data)
                db.session.commit()
                flash('Photo add to tree successful')
            else:
                if form.title.data:
                    photo_meta_data.title = form.title.data
                if description:
                    photo_meta_data.description = description
                if form.location.data:
                    photo_meta_data.location = form.location.data
                if form.creation_date.data:
                    photo_meta_data.creation_data = form.creation_date.data

                db.session.commit()
                flash('Update successful')

        return redirect(url_for('user_photos'))

    else:
        return redirect(url_for('auth.login'))


@photos.route('/add_editing_permission', methods=['GET', 'POST'])
def add_editing_permission():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))

        if request.method == "POST":

            photos_data = request.form.getlist('selected_users')
            photo_id = request.form['photo_id']
            for email in photos_data:
                user = Users.query.filter_by(email=email).first()
                permissions = EditingPermission(photo_id=photo_id, email=user.email, editable=True)
                db.session.add(permissions)
            db.session.commit()
        return redirect(url_for('user_photos'))
    else:
        return redirect(url_for('auth.login'))


@photos.route('/people', methods=['GET', 'POST'])
def people():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        current_user_family = Users.query.filter_by(parent_id=current_user.parent_id).all()
        face_encode = []
        for family_user in current_user_family:
            people_face = FaceEncode.query.filter_by(user_id=family_user.id).all()
            for face in people_face:
                decoded_face = pickle.loads(face.face_encode)
                face_encode.append({face.photo_id: decoded_face})
        family_face_recognition = db_handler.face_recognition_handler(face_encode)
        faces = []
        for i in family_face_recognition:
            for _, photo_ids in i.items():
                family_user_photos = []
                for photo_id in photo_ids:
                    family_user_photos.append(Photos.query.filter_by(id=photo_id).first())
                faces.append(db_handler.get_photos_from_db(family_user_photos, session['credentials']))

        return render_template('photo_templates/people.html', faces=faces)
    else:
        return redirect(url_for('auth.login'))

