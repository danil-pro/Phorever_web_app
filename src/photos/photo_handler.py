# import json
import os.path
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
from src.photos.FaceEncodeHandler import FaceEncodeHandler
from src.oauth2.oauth2 import authenticator
from src.app.Forms import UpdateForm, UpdateLocationForm, UpdateCreationDateForm, AddFaceName, AddFamilyMemberForm

import asyncio
import shutil
import datetime

import src.photos.Handler as Handler
# import numpy as np
# import json
from pyicloud import PyiCloudService
import keyring
from pyicloud.exceptions import PyiCloudNoStoredPasswordAvailableException

photos = Blueprint('photos', __name__, template_folder='../templates/photo_templates', static_folder='../static')

db_handler = DBHandler()

# handler = src.photos.Handler


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
                    photos_data, next_page_token = Handler.photo_from_google(credentials, next_page_token)
                else:
                    photos_data, next_page_token = Handler.photo_from_google(credentials, None)
            else:
                photos_data, next_page_token = Handler.photo_from_google(credentials, None)

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
            if photos_data:
                source_function = request.form.get('source_function')
                face_encode_handler = FaceEncodeHandler()
                result = []
                if source_function == '/photos/google_photos':
                    result = face_encode_handler.download_photos(session['credentials'], photos_data, source_function)
                elif source_function == '/photos/icloud_photos':
                    result = face_encode_handler.download_photos(session['icloud_credentials'], photos_data,
                                                                 source_function)
                for photo_data in photos_data:
                    photo_id, photo_url = photo_data.split('|')
                    if source_function == '/photos/google_photos':
                        photo = Photos(photos_data=photo_id, photos_url=photo_url, service=source_function,
                                       token=session['credentials']['token'],
                                       refresh_token=session['credentials']['refresh_token'],
                                       apple_id=None,
                                       user_id=current_user.id)
                        db.session.add(photo)
                    elif source_function == '/photos/icloud_photos':
                        photo = Photos(photos_data=photo_id, photos_url=photo_url, service=source_function,
                                       token=None,
                                       refresh_token=None,
                                       apple_id=session['icloud_credentials']['apple_id'],
                                       user_id=current_user.id)
                        db.session.add(photo)
                db.session.commit()
                for photo_id, face_encode in result.items():
                    photo = Photos.query.filter_by(photos_data=photo_id).first()
                    for faces in face_encode:
                        code = Handler.generate_unique_code()
                        face = FaceEncode(face_encode=faces,
                                          photo_id=photo.id,
                                          face_code=code,
                                          key_face=None,
                                          user_id=current_user.id)
                        db.session.add(face)
                    db.session.commit()

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
            api.authenticate(force_refresh=True)
            photo_ids = set()
            data_url = []

            for photo in api.photos.albums['All Photos']:
                for version, data in photo.versions.items():
                    if data['type'] == 'public.jpeg' and photo.id not in photo_ids:
                        data_url.append({photo.id: data['url']})
                        photo_ids.add(photo.id)

            user_photo_ids = [photo.photos_data for photo in Photos.query.filter().all()
                              if photo.service == '/photos/icloud_photos']
            if not data_url:
                flash('No photo', 'info')
                return render_template('photo_templates/img.html', source_function=url_for('photos.icloud_photos'))
            for user_photo_id in user_photo_ids:
                for data in data_url:
                    if user_photo_id == next(iter(data)):
                        data_url.remove(data)

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
        faces_directory = os.path.join(os.path.dirname(__file__), '..', '..', 'static',
                                       'img', 'user_photos', 'faces')
        current_user_family = Users.query.filter_by(parent_id=current_user.parent_id).all()
        face_encode = []
        for family_user in current_user_family:
            people_face = FaceEncode.query.filter_by(user_id=family_user.id).all()
            for face in people_face:
                decoded_face = pickle.loads(face.face_encode)
                face_encode.append({face.photo_id: [decoded_face, face.face_code]})
        list_face_code = Handler.face_folders(face_encode, session, current_user.parent_id)
        items_to_remove = []
        for i in list_face_code:
            for photo_id, path in i.items():
                existing_files = [file for root, dirs, files in os.walk(faces_directory) for file in files]
                people_name = FaceEncode.query.filter_by(face_code=path[1]).first()
                if people_name.name:
                    path.append(people_name.name)
                else:
                    path.append('')
                if f'{people_name.key_face}.jpeg' not in existing_files:
                    folder_path = os.path.join(faces_directory, path[0].split('/')[0])
                    items_to_remove.append(i)
                    if os.path.exists(folder_path):
                        shutil.rmtree(folder_path)

        for item in items_to_remove:
            list_face_code.remove(item)
        # print(list_face_code)
        session['list_face_code'] = list_face_code

        return render_template('photo_templates/people.html', face_dir=list_face_code)
    else:
        return redirect(url_for('auth.login'))


@photos.route('/people/<face_code>', methods=['GET', 'POST'])
def one_face_people(face_code):
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        add_face_name = AddFaceName(request.form)
        add_family_member_form = AddFamilyMemberForm(request.form)

        people_name = FaceEncode.query.filter_by(face_code=face_code).first()
        current_user_family = Users.query.filter_by(parent_id=current_user.parent_id).all()
        face_encode = []

        for family_user in current_user_family:
            people_face = FaceEncode.query.filter_by(user_id=family_user.id).all()
            for face in people_face:
                decoded_face = pickle.loads(face.face_encode)
                face_encode.append({face.photo_id: [decoded_face, face.face_code]})
        face_encode_handler = FaceEncodeHandler()
        family_face_recognition = face_encode_handler.face_recognition_handler(face_encode)
        faces = []
        for i in family_face_recognition:
            family_user_photos = []
            for photo_id, photo_ids in i.items():
                if photo_ids[0] == face_code:
                    for j in photo_ids[1]:
                        family_user_photos.append(Photos.query.filter_by(id=j).first())
            faces.append(db_handler.get_photos_from_db(family_user_photos, session['credentials']))
        if request.method == 'POST' and add_face_name.validate_on_submit():
            people_faces = FaceEncode.query.filter_by(key_face=face_code).all()
            for people_face in people_faces:
                people_face.name = add_face_name.face_name.data
            db.session.commit()
            return redirect(url_for('photos.people'))

        for face in faces:
            for photo_id, data in face.items():
                photos_meta_data = PhotosMetaData.query.filter_by(photo_id=photo_id).first()
                if not photos_meta_data:
                    continue
                    # photos_data[photo_id] = {'baseUrl': data['baseUrl'],
                    #                          'title': 'Empty title',
                    #                          'description': data['description'],
                    #                          'location': 'Empty location',
                    #                          'creation_data': data['creationTime']}
                else:
                    data['title'] = photos_meta_data.title
                    data['description'] = photos_meta_data.description
                    data['location'] = photos_meta_data.location
                    data['creation_data'] = photos_meta_data.creation_data
                    # photos_data[photo_id] = {'baseUrl': data['baseUrl'],
                    #                          'title': photos_meta_data.title,
                    #                          'description': photos_meta_data.description,
                    #                          'location': photos_meta_data.location,
                    #                          'creation_data': photos_meta_data.creation_data}

        return render_template('photo_templates/one_face_people.html', faces=faces, add_face_name=add_face_name,
                               face_code=face_code, name=people_name.name,
                               add_family_member_form=add_family_member_form, list_face_code=session['list_face_code'],
                               face_path='/'.join([face_code[i:i+2] for i in range(0, len(face_code), 2)]))
    else:
        return redirect(url_for('auth.login'))


@photos.route('/family_tree', methods=['GET', 'POST'])
def family_tree():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        form = AddFamilyMemberForm(request.form)
        if request.method == "POST":
            pass
        return redirect(url_for('photos.people'))
    else:
        return redirect(url_for('auth.login'))