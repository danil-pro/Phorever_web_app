import time

import flask
from flask import *
from src.auth.auth import current_user, send_email
from flask_jwt_extended import jwt_required, get_jwt_identity

from google.oauth2.credentials import Credentials

from dropbox.exceptions import AuthError
import dropbox
from dropbox import files, sharing

# from src.app.config import *
from src.app.model import db, Photo, User, PhotoMetaData, EditingPermission, FaceEncode, Person, Message
from src.photos.DBHandler import DBHandler
from src.face_recognition.download_photos import download_photos
from src.oauth2.oauth2 import authenticator, google_authorize, check_credentials
from src.app.Forms import UpdateForm, UpdateLocationForm, UpdateCreationDateForm, AddCommentForm
from datetime import datetime
from src.face_recognition.download_photos import face_encode_handler

import asyncio

import src.photos.Handler as Handler
from celery.result import allow_join_result

# import json
from pyicloud import PyiCloudService
import keyring
from pyicloud.exceptions import (PyiCloudNoStoredPasswordAvailableException, PyiCloudFailedLoginException,
                                 PyiCloudServiceNotActivatedException)
from flask_restful import Api, Resource, reqparse
from celery import group, chord

photos = Blueprint('photos', __name__, template_folder='../templates/photo_templates', static_folder='../static')

db_handler = DBHandler()
api = Api()


# handler = src.photos.Handler
# family_tree_relationships = FamilyTree()


@photos.route('/google_photos', methods=['GET', 'POST'])
def google_photos():
    if current_user.is_authenticated:
        if (current_user.google_token is None or current_user.google_refresh_token is None or
                time.time() - current_user.google_credentials_create_at >= 24 * 60 * 60):
            return redirect(url_for('oauth2.google_authorize'))
        credentials = check_credentials()
        try:
            credentials = Credentials.from_authorized_user_info(credentials)

            if request.method == "POST":
                if 'next_page' in request.form:
                    next_page_token = request.form.get('next_page_token')
                    photos_data, next_page_token = Handler.photo_from_google(credentials, next_page_token)
                else:
                    photos_data, next_page_token = Handler.photo_from_google(credentials, None)
            else:
                photos_data, next_page_token = Handler.photo_from_google(credentials, None)

            user_photo_ids = [photo.photos_data for photo in Photo.query.filter().all()
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
        download_tasks = []
        credentials = check_credentials()
        if request.method == 'POST':
            photos_data = request.form.getlist('selected_photos')
            if photos_data:
                source_function = request.form.get('source_function')
                for photo_data in photos_data:
                    photo_id, photo_url = photo_data.split('|')
                    photo = Photo(photos_data=photo_id,
                                  photos_url=photo_url,
                                  service=source_function,
                                  token=current_user.google_token
                                  if source_function == '/photos/google_photos' else None,
                                  refresh_token=current_user.google_refresh_token
                                  if source_function == '/photos/google_photos' else None,
                                  apple_id=None
                                  if source_function == '/photos/google_photos' else current_user.apple_id,
                                  user_id=current_user.id)
                    db.session.add(photo)
                    db.session.commit()
                    download_tasks.append(download_photos.s(credentials, photo_id, source_function, current_user.id))

            task_group = group(download_tasks)
            callback = face_encode_handler.s(current_user.id)
            chord(task_group)(callback)

            # face_encode_handler(current_user.id, credentials)

            # db.session.commit()

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
        try:
            if not current_user.apple_id:
                return redirect(url_for('oauth2.icloud_authorize'))
            icloud_password = keyring.get_password("pyicloud", current_user.apple_id)
            if not icloud_password:
                return redirect(url_for('oauth2.icloud_authorize'))
            api = PyiCloudService(current_user.apple_id, icloud_password)
            api.authenticate(force_refresh=True)
            print(api.photos.albums.keys())

            photo_ids = set()
            data_url = []

            for photo in api.photos.albums['All Photos']:
                for version, data in photo.versions.items():
                    print(data['type'])
                    if photo.id not in photo_ids:
                        if data['type'] == 'public.jpeg':
                            data_url.append({'url': data['url'], 'photo_id': photo.id})
                            photo_ids.add(photo.id)
            user_photo_ids = [photo.photos_data for photo in Photo.query.filter().all()
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
        except PyiCloudFailedLoginException:
            return redirect(url_for('oauth2.icloud_authorize'))
        except PyiCloudServiceNotActivatedException:
            return redirect(url_for('oauth2.icloud_authorize'))
    return redirect(url_for('auth.login'))


@photos.route('/<photo_id>')
def one_photo(photo_id):
    if current_user.is_authenticated:
        form = UpdateForm(request.form)
        comment_form = AddCommentForm(request.form)
        photo = Photo.query.filter_by(id=photo_id).first()
        user = User.query.filter_by(id=photo.user_id).first()
        photo_meta_data = PhotoMetaData.query.filter_by(photo_id=photo_id).first()
        face_encode = FaceEncode.query.filter_by(photo_id=photo_id).all()
        current_user_family = User.query.filter_by(parent_id=current_user.parent_id).all()
        family_users = []

        for family_user in current_user_family:
            family_users.append(family_user.email)
        persons = []
        for person in face_encode:
            person_data = Person.query.filter_by(face_code=person.key_face).first()
            if person_data:
                face_url = (f"../../static/img/user_photos/faces/"
                            f"{'/'.join([person.key_face[i:i + 2] for i in range(0, len(person.key_face), 2)])}"
                            f"/{person.key_face}.jpeg")
                person_name = person_data.name
                person_face_code = person.key_face
                persons.append({'face_url': face_url,
                                'person_name': person_name,
                                'person_face_code': person_face_code})
        photo_data = {
            'photo_id': photo_id,
            'user': user.email,
            'photo_url': photo.photos_url,
            'title': photo_meta_data.title,
            'description': photo_meta_data.description,
            'location': photo_meta_data.location,
            'creation_data': datetime.fromtimestamp(photo_meta_data.creation_data).date(),
            'persons': persons

        }
        unique_sender_emails = []
        if photo.user_id == user.id:
            comments = Message.query.filter_by(photo_id=photo_id).all()
            for comment in comments:
                if comment.sender.email not in unique_sender_emails:
                    unique_sender_emails.append(comment.sender.email)

        else:
            comments = Message.query.filter(
                (Message.photo_id == photo_id) &
                ((Message.sender_id == user.id) | (Message.recipient_id == user.id))
            ).all()

        return render_template('photo_templates/photo.html', photo_data=photo_data,
                               permissions=EditingPermission, form=form, family_users=family_users,
                               comment_form=comment_form, comments=comments, unique_sender_emails=unique_sender_emails)
    else:
        return redirect(url_for('auth.login'))


@photos.route('/update_media_meta_data', methods=['GET', 'POST'])
def update_media_meta_data():
    if current_user.is_authenticated:
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
                            photo_meta_data = PhotoMetaData.query.filter_by(photo_id=photo_id).first()
                            if not photo_meta_data:
                                new_photo_meta_data = PhotoMetaData(title='Empty title',
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
                            photo_meta_data = PhotoMetaData.query.filter_by(photo_id=photo_id).first()
                            if not photo_meta_data:
                                new_photo_meta_data = PhotoMetaData(title='Empty title',
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
        form = UpdateForm(request.form)
        if request.method == "POST" and form.validate_on_submit():
            description = request.form['description']
            photo_id = request.form['photo_id']

            photo_meta_data = PhotoMetaData.query.filter_by(photo_id=photo_id).first()

            if not photo_meta_data:
                new_photo_meta_data = \
                    PhotoMetaData(title=form.title.data,
                                  description=description,
                                  location=form.location.data,
                                  creation_data=int(
                                      datetime.combine(form.creation_date.data, datetime.min.time()).timestamp()),
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
                    photo_meta_data.creation_data = int(
                        datetime.combine(form.creation_date.data, datetime.min.time()).timestamp())

                db.session.commit()
                flash('Update successful')

        return redirect(url_for('user_photos'))

    else:
        return redirect(url_for('auth.login'))


@photos.route('/add_editing_permission', methods=['GET', 'POST'])
def add_editing_permission():
    if current_user.is_authenticated:
        if request.method == "POST":
            photos_data = request.form.getlist('selected_users')
            photo_id = request.form['photo_id']
            for email in photos_data:
                user = User.query.filter_by(email=email).first()
                permissions = EditingPermission(photo_id=photo_id, email=user.email, editable=True)
                db.session.add(permissions)
                send_email(email, 'Photo Editing Permission Granted',
                           f'''
Hello,

We are writing to let you know that {current_user.email} has granted you permission to edit the photo.

You can now edit the photo by visiting the following link:
{url_for('photos.one_photo', photo_id=photo_id, _external=True)}

Please respect the original intent and content of the photo, and adhere to our community guidelines when making edits.

If you have any questions or encounter any issues, please do not hesitate to contact our support team.

Happy editing!

Best regards,
Phorever
                ''')
            db.session.commit()
        return redirect(url_for('user_photos'))
    else:
        return redirect(url_for('auth.login'))


# google_data = reqparse.RequestParser()
# google_data.add_argument("next_page_token", type=str, help="next_page_token")
# google_data.add_argument("limit", type=int, help="limit")


def get_google_photos(next_page_token=None, limit=100):
    api_current_user = User.query.filter_by(id=get_jwt_identity()).first()
    time_difference = time.time() - api_current_user.google_credentials_create_at
    if time_difference >= 24 * 60 * 60:
        return {'google_uri': google_authorize(api_current_user.id)}
    credentials = check_credentials(api_current_user.id, 'google')
    try:
        credentials = Credentials.from_authorized_user_info(credentials)
        new_next_page_token = None
        if next_page_token:
            photos_data, new_next_page_token = Handler.photo_from_google(credentials, next_page_token, limit)
        else:
            photos_data, new_next_page_token = Handler.photo_from_google(credentials, None, limit)

        user_photo_ids = [photo.photos_data for photo in Photo.query.filter().all()
                          if photo.service == '/photos/google_photos']
        if not photos_data:
            return {'message': 'no photos', 'next_page_token': new_next_page_token}
        for user_photo_id in user_photo_ids:
            for data in photos_data:
                if user_photo_id == data['photoId']:
                    photos_data.remove(data)

        return {'success': True, 'data': {'google_photos_data': photos_data,
                                          'next_page_token': new_next_page_token,
                                          'message': 'OK'}}, 200
    except AuthError as e:
        return {'google_uri': google_authorize(api_current_user.id)}


def get_icloud_photos():
    api_current_user = User.query.filter_by(id=get_jwt_identity()).first()
    try:
        if api_current_user.apple_id is None:
            return {'icloud_uri': url_for('oauth2.icloud_authorize', user=api_current_user.email, _external=True)}
        api = api_current_user.icloud_api()
        if type(api) is dict and 'icloud_uri' in api:
            return api
        photo_ids = set()
        data_url = []

        for photo in api.photos.albums['All Photo']:
            for version, data in photo.versions.items():
                date_object = datetime.fromisoformat(str(photo.created))
                unix_time = int(date_object.timestamp())

                if data['type'] == 'public.jpeg' and photo.id not in photo_ids:
                    data_url.append({'photoId': photo.id, 'baseUrl': data['url'],
                                     'creationTime': unix_time})
                    photo_ids.add(photo.id)

        user_photo_ids = [photo.photos_data for photo in Photo.query.filter().all()
                          if photo.service == '/photos/icloud_photos']
        if not data_url:
            return {'message': 'no photos'}
        for user_photo_id in user_photo_ids:
            for data in data_url:
                if user_photo_id == next(iter(data)):
                    data_url.remove(data)

        return {'success': True, 'data': {'google_photos_data': data_url,
                                          'message': 'OK'}}, 200

    except PyiCloudNoStoredPasswordAvailableException:
        return {'icloud_uri': url_for('oauth2.icloud_authorize', user=api_current_user.email, _external=True)}
    except PyiCloudFailedLoginException:
        return {'icloud_uri': url_for('oauth2.icloud_authorize', user=api_current_user.email, _external=True)}


api_photos_data = reqparse.RequestParser()
api_photos_data.add_argument("data", type=dict, action="append", help="photos_data is required", required=True)

api_meta_data = reqparse.RequestParser()
api_meta_data.add_argument("title", type=str)
api_meta_data.add_argument("description", type=str)
api_meta_data.add_argument("location", type=str)
api_meta_data.add_argument("creation_time", type=str)

service_data = reqparse.RequestParser()
service_data.add_argument("service", type=str)
service_data.add_argument("next_page_token", type=str, help="next_page_token")
service_data.add_argument("limit", type=int, help="limit")
service_data.add_argument("apple_id", type=str, help="limit")
service_data.add_argument("password", type=str, help="limit")


class UserPhoto(Resource):
    @jwt_required()
    def get(self):
        args = service_data.parse_args()
        if args.get('service') == 'google':
            google_photos_provider = get_google_photos(args.get('next_page_token'), args.get('limit'))
            return google_photos_provider
        elif args.get('service') == 'icloud':
            return get_icloud_photos()
        api_current_user = User.query.filter_by(id=get_jwt_identity()).first()
        credentials = check_credentials(api_current_user.id, 'google')
        if args.get('limit'):
            family_photos = Photo.query.filter(User.parent_id == api_current_user.parent_id,
                                               Photo.user_id == User.id).limit(args.get('limit')).all()
        else:
            family_photos = Photo.query.filter(User.parent_id == api_current_user.parent_id,
                                               Photo.user_id == User.id).all()
        photo_urls = db_handler.get_photos_from_db(family_photos, credentials)

        current_user_family = User.query.filter_by(parent_id=api_current_user.parent_id).all()

        photo_data = {}

        for family_user in current_user_family:
            photos_data = []
            for data in photo_urls:
                photos_meta_data = PhotoMetaData.query.filter_by(photo_id=data['photo_id']).first()
                if not photos_meta_data:
                    photos_data.append({'baseUrl': data['baseUrl'],
                                        'title': 'Empty title',
                                        'description': data['description'],
                                        'location': 'Empty location',
                                        'creation_data': data['creationTime'],
                                        'photo_id': data['photo_id']})
                else:
                    photos_data.append({'baseUrl': data['baseUrl'],
                                        'title': photos_meta_data.title,
                                        'description': photos_meta_data.description,
                                        'location': photos_meta_data.location,
                                        'creation_data': photos_meta_data.creation_data,
                                        'photo_id': data['photo_id']})
            # print(photos_data)
            for data in photos_data:
                user_photo = Photo.query.filter_by(id=data['photo_id']).first()
                if family_user.id == user_photo.user_id:
                    if family_user.email not in photo_data:
                        photo_data[family_user.email] = []
                    photo_data[family_user.email].append(data)
        return {"success": True, "data": {'user_photo': photo_data, 'message': 'OK'}}, 200

    @jwt_required()
    def post(self):
        api_current_user = User.query.filter_by(id=get_jwt_identity()).first()
        credentials = check_credentials(api_current_user.id, 'google')

        if api_current_user.google_token is None or api_current_user.google_refresh_token is None:
            return {'google_uri': google_authorize(api_current_user.id)}

        photos_data = api_photos_data.parse_args()
        download_tasks = []

        if photos_data:
            source_function = None
            for photo_data in photos_data['data']:
                if 'googleusercontent.com' in photo_data['photo_url']:
                    source_function = '/photos/google_photos'
                else:
                    source_function = '/photos/icloud_photos'
                if not photo_data.get('photo_id'):
                    return {'message': 'Invalid photo data: missing photo_id'}, 400

                if Photo.query.filter_by(photos_data=photo_data['photo_id']).first():
                    return {'message': 'Photo is exist'}, 409
                try:
                    photos_url = photo_data.get('photo_url', '')
                    if not photos_url:
                        raise ValueError('Empty photos_url')
                    photo = Photo(photos_data=photo_data['photo_id'],
                                  photos_url=photo_data['photo_url'],
                                  service=source_function,
                                  token=current_user.google_token
                                  if source_function == '/photos/google_photos' else None,
                                  refresh_token=current_user.google_refresh_token
                                  if source_function == '/photos/google_photos' else None,
                                  apple_id=None
                                  if source_function == '/photos/google_photos' else current_user.apple_id,
                                  user_id=current_user.id)
                    db.session.add(photo)
                    db.session.commit()
                    download_tasks.append(
                        download_photos.s(credentials, photo_data['photo_id'], source_function, api_current_user.id))

                    title = photo_data.get('title', 'Empty title')
                    description = photo_data.get('description', 'Empty description')
                    location = photo_data.get('location', 'Empty location')
                    creation_data = photo_data.get('creation_data', int(time.time()))
                    print(creation_data)

                    photo_metadata = PhotoMetaData(title=title,
                                                   description=description,
                                                   location=location,
                                                   creation_data=creation_data,
                                                   photo_id=photo.id)

                    db.session.add(photo_metadata)
                except ValueError as ve:
                    db.session.rollback()
                    return {'message': f'Invalid data format: {ve}'}, 400
                except Exception as e:
                    db.session.rollback()
                    return {'message': f'Invalid data format in one of the fields, error: {e}'}, 400

                db.session.commit()

            db.session.commit()

        task_group = group(download_tasks)
        callback = face_encode_handler.s(current_user.id)
        chord(task_group)(callback)

        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200

    @jwt_required()
    def put(self, photo_id):
        api_current_user = User.query.filter_by(id=get_jwt_identity()).first()
        photo = Photo.query.filter_by(id=photo_id).first()
        permissions = EditingPermission.query.filter_by(photo_id=photo_id).all()
        permissions_email = [permission.email for permission in permissions if permission.editable == True]

        photo_meta_data = PhotoMetaData.query.filter_by(photo_id=photo_id).first()
        args = api_meta_data.parse_args()

        title = args.get('title')
        description = args.get('description')
        location = args.get('location')
        creation_data = args.get('creation_time')
        if photo:
            if photo.user_id == api_current_user.id or api_current_user.email in permissions_email:
                if not photo_meta_data:
                    new_photo_meta_data = PhotoMetaData(title=title, description=description,
                                                        location=location, creation_data=creation_data,
                                                        photo_id=photo_id)
                    db.session.add(new_photo_meta_data)
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
            else:
                return {'message': f'User {api_current_user.email} '
                                   f'does not have permissions to update photo meta data '}, 403
        else:
            return {'message': f'Photo id: {photo_id} does not exist'}, 404

        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200


update_meta_data = reqparse.RequestParser()
update_meta_data.add_argument('selected_photos', type=int, action="append",
                              help='Comma-separated list of selected photo IDs',
                              required=True)
update_meta_data.add_argument('metadata_type', type=str,
                              help='Type of metadata to update (location or creation_date)', required=True)
update_meta_data.add_argument('metadata', type=str,
                              help='metadata is required', required=True)

users_for_permissions = reqparse.RequestParser()
users_for_permissions.add_argument('users', type=str, action="append", help='users is required', required=True)


class UpdateUserPhotoData(Resource):
    @jwt_required()
    def put(self):
        api_current_user = User.query.filter_by(id=get_jwt_identity()).first()

        args = update_meta_data.parse_args()
        selected_photo = args.get('selected_photos')
        metadata_type = args.get('metadata_type')
        metadata = args.get('metadata')

        if metadata_type not in ('location', 'creation_date'):
            return {'error': 'metadata_type should be "location" or "creation_date"'}, 400
        for photo_id in selected_photo:
            photo = Photo.query.filter_by(id=photo_id).first()
            permissions = EditingPermission.query.filter_by(photo_id=photo_id).all()
            permissions_email = [permission.email for permission in permissions if permission.editable == True]
            if photo:
                if photo.user_id == api_current_user.id or api_current_user.email in permissions_email:

                    if metadata_type == 'location':
                        photo_meta_data = PhotoMetaData.query.filter_by(photo_id=photo_id).first()

                        if not photo_meta_data:
                            new_photo_meta_data = PhotoMetaData(title='Empty title',
                                                                description='Empty description',
                                                                location=metadata,
                                                                photo_id=photo_id)
                            db.session.add(new_photo_meta_data)
                        else:
                            photo_meta_data.location = metadata
                            db.session.add(photo_meta_data)
                    elif metadata_type == 'creation_date':
                        photo_meta_data = PhotoMetaData.query.filter_by(photo_id=photo_id).first()
                        if not photo_meta_data:
                            new_photo_meta_data = PhotoMetaData(title='Empty title',
                                                                description='Empty description',
                                                                location='Empty location',
                                                                creation_data=metadata,
                                                                photo_id=photo_id)
                            db.session.add(new_photo_meta_data)
                        else:
                            photo_meta_data.creation_data = metadata
                            db.session.add(photo_meta_data)
                    db.session.commit()
                else:
                    return {'message': f'User {api_current_user.email} '
                                       f'does not have permissions to update photo meta data '}, 403
            else:
                return {'message': f'Photo id: {photo_id} does not exist'}, 404
        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200

    @jwt_required()
    def post(self, photo_id):
        args = users_for_permissions.parse_args()
        photos_data = args.get('users')
        photos_data = photos_data.split(',')  # Разделяем строку по запятой
        photos_data = [email for email in photos_data]  # Преобразуем в числа (если необходимо)

        for email in photos_data:
            user = User.query.filter_by(email=email).first()
            if user:
                permissions = EditingPermission(photo_id=photo_id, email=user.email, editable=True)
                db.session.add(permissions)
            else:
                return {'message': f'User {email} does not exist'}, 404
        db.session.commit()
        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200


api.add_resource(UpdateUserPhotoData, '/api/v1/photo/batch', '/api/v1/photo/add_permission/<int:photo_id>')
api.add_resource(UserPhoto, '/api/v1/photo', '/api/v1/photo/<int:photo_id>')
