import time

from celery import group, chord
from dropbox.exceptions import AuthError
from flask import *
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Api, Resource, reqparse
from google.oauth2.credentials import Credentials
# import json
# from pyicloud.exceptions import (PyiCloudNoStoredPasswordAvailableException, PyiCloudFailedLoginException)

# import src.photos.Handler as Handler
from src.app.Forms import UpdateForm, UpdateLocationForm, UpdateCreationDateForm, AddCommentForm
# from src.app.config import *
from src.app.model import db, Photo, User, PhotoMetaData, Permission, FaceEncode, Person, Message
from src.app.utils import get_user_by_id
from src.auth.auth import current_user, send_email
from src.face_recognition.download_photos import download_photos
from src.face_recognition.download_photos import face_encode_handler
from src.oauth2.oauth2 import google_authorize, check_credentials

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError
from flask import redirect, url_for

from datetime import datetime
from src.app.config import *

from src.photos.DBHandler import DBHandler

photos = Blueprint('photos', __name__, template_folder='../templates/photo_templates', static_folder='../static')

db_handler = DBHandler()
api = Api()


def photo_init_app(app):
    api.init_app(app)


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
                    photo_data, next_page_token = UserPhoto.photo_from_google(credentials, next_page_token)
                else:
                    photo_data, next_page_token = UserPhoto.photo_from_google(credentials, None)
            else:
                photo_data, next_page_token = UserPhoto.photo_from_google(credentials, None)

            user_photo_ids = [photo.photo_data for photo in Photo.query.filter().all()
                              if photo.service == '/photos/google_photos']
            if not photo_data:
                flash('No photo', 'info')
                return render_template('photo_templates/img.html', source_function=url_for('photos.google_photos'))
            for user_photo_id in user_photo_ids:
                for data in photo_data:
                    if user_photo_id == data['photoId']:
                        photo_data.remove(data)

            return render_template('photo_templates/img.html', base_url=photo_data,
                                   source_function=url_for('photos.google_photos'),
                                   next_page_token=next_page_token)
        except AuthError as e:
            print(e)
    return redirect(url_for('auth.login'))


@photos.route('/add_photo', methods=['GET', 'POST'])
def add_photo():
    if current_user.is_authenticated:
        download_tasks = []
        if request.method == 'POST':
            photo_data = request.form.getlist('selected_photos')
            if photo_data:
                for photo_data in photo_data:
                    photo_id, photo_url = photo_data.split('|')
                    photo = Photo(photo_data=photo_id,
                                  photo_url=photo_url,
                                  service='/photos/google_photos',
                                  token=current_user.google_token,
                                  refresh_token=current_user.google_refresh_token,
                                  user_id=current_user.id)
                    db.session.add(photo)
                    db.session.flush()

                    photo_metadata = PhotoMetaData(title=None,
                                                   description=None,
                                                   location=None,
                                                   creation_data=None,
                                                   photo_id=photo.id)

                    db.session.add(photo_metadata)
                    db.session.commit()

                    download_tasks.append(download_photos.s(photo_url, photo.id, current_user.id))
            task_group = group(download_tasks)
            callback = face_encode_handler.s(current_user.id)
            chord(task_group)(callback)

            return redirect(url_for('user_photos'))
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
            'photo_url': photo.photo_url,
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
                               permissions=Permission, form=form, family_users=family_users,
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
            photo_data = request.form.getlist('selected_users')
            photo_id = request.form['photo_id']
            for email in photo_data:
                user = User.query.filter_by(email=email).first()
                permissions = Permission(target_id=photo_id, email=user.email, editable=True)
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


def get_google_photos(next_page_token=None, limit=100):
    api_current_user = User.query.filter_by(id=get_jwt_identity()).first()
    if api_current_user.google_credentials_create_at is None:
        return {'google_uri': google_authorize(api_current_user.id)}
    time_difference = time.time() - api_current_user.google_credentials_create_at

    if time_difference >= 24 * 60 * 60:
        return {'google_uri': google_authorize(api_current_user.id)}
    credentials = check_credentials(api_current_user.id, 'google')
    try:
        credentials = Credentials.from_authorized_user_info(credentials)
        if next_page_token:
            photo_data, new_next_page_token = UserPhoto.photo_from_google(credentials, next_page_token, limit)
        else:
            photo_data, new_next_page_token = UserPhoto.photo_from_google(credentials, None, limit)

        user_photo_ids = [photo.photo_data for photo in Photo.query.filter().all()
                          if photo.service == '/photos/google_photos']
        if not photo_data:
            return {'message': 'no photos', 'next_page_token': new_next_page_token}
        for user_photo_id in user_photo_ids:
            for data in photo_data:
                if user_photo_id == data['photoId']:
                    photo_data.remove(data)

        return {'success': True, 'data': {'google_photo_data': photo_data,
                                          'next_page_token': new_next_page_token,
                                          'message': 'OK'}}, 200
    except AuthError as e:
        return {'google_uri': google_authorize(api_current_user.id)}


api_photo_data = reqparse.RequestParser()
api_photo_data.add_argument("data", type=dict, action="append", help="photo_data is required", required=True)

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
        user_id = get_jwt_identity()
        args = service_data.parse_args()
        if args.get('service') == 'google':
            return get_google_photos(args.get('next_page_token') if args.get('next_page_token') else None,
                                     args.get('limit'))

        return self.get_family_photos(user_id, args.get('limit'))

    def get_family_photos(self, user_id, limit=None):
        api_current_user = get_user_by_id(user_id)

        query = Photo.query.join(User, User.id == Photo.user_id).filter(User.parent_id == api_current_user.parent_id)
        if limit:
            family_photos = query.limit(limit).all()
        else:
            family_photos = query.all()

        return {"success": True, "data": {'user_photo': self.build_photo_data(family_photos), 'message': 'OK'}}, 200

    @staticmethod
    def build_photo_data(family_photos):
        return [
            {
                'baseUrl': photo.photo_url,
                'title': photo.meta_data.title if photo.meta_data else '',
                'description': photo.meta_data.description if photo.meta_data else '',
                'location': photo.meta_data.location if photo.meta_data else '',
                'creation_data': photo.meta_data.creation_data if photo.meta_data else '',
                'photo_id': photo.id,
                'photo_owner': photo.user.email
            } for photo in family_photos
        ]

    @jwt_required()
    def post(self):
        user = get_user_by_id(get_jwt_identity())

        if (user.google_token is None or
                user.google_refresh_token is None):
            return {'google_uri': google_authorize(get_jwt_identity())}

        photo_data = api_photo_data.parse_args()
        download_tasks = []
        if photo_data:
            for photo_data in photo_data['data']:
                if not photo_data.get('photo_id'):
                    return {'message': 'Invalid photo data: missing photo_id'}, 400

                if Photo.query.filter_by(photo_data=photo_data['photo_id']).first():
                    return {'message': 'Photo is exist'}, 409
                try:
                    photo_url = photo_data.get('photo_url', '')
                    if not photo_url:
                        raise ValueError('Empty photo_url')
                    photo = Photo(photo_data=photo_data['photo_id'],
                                  photo_url=photo_data['photo_url'],
                                  service='/photos/google_photos',
                                  token=user.google_token,
                                  refresh_token=user.google_refresh_token,
                                  user_id=user.id)
                    db.session.add(photo)
                    db.session.commit()
                    download_tasks.append(download_photos.s(photo_data['photo_url'], photo.id, user.id))

                    title = photo_data.get('title', None)
                    description = photo_data.get('description', None)
                    location = photo_data.get('location', None)
                    creation_data = photo_data.get('creation_data', None)

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
        callback = face_encode_handler.s(user.id)
        chord(task_group)(callback)

        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200

    @staticmethod
    def photo_from_google(credentials, page_token=None, limit=100):
        photos_data = []
        try:
            service = build(API_SERVICE_NAME, API_VERSION, credentials=credentials, static_discovery=False)
            if page_token:
                results = service.mediaItems().list(
                    pageSize=limit,
                    pageToken=page_token,
                ).execute()
            else:
                results = service.mediaItems().list(
                    pageSize=limit
                ).execute()
            items = results.get('mediaItems', [])
            for item in items:
                media_meta_data = item.get('mediaMetadata')
                video = media_meta_data.get('video')
                date = media_meta_data.get('creationTime')
                date_obj = datetime.fromisoformat(date[:-1])
                timestamp = date_obj.timestamp()
                description = item.get('description')
                if not video:
                    photo_data = {'baseUrl': item.get('baseUrl'), 'photoId': item.get('id'),
                                  'creationTime': timestamp,
                                  'description': description if description else ''}

                    photos_data.append(photo_data)
            next_page_token = results.get('nextPageToken')
        except HttpError as error:
            print(f"An error occurred: {error}")
            return [], None
        except RefreshError:
            return redirect(url_for('oauth2.google_authorize'))
        return photos_data, next_page_token


update_meta_data = reqparse.RequestParser()
update_meta_data.add_argument('selected_photos', type=int, action="append",
                              help='Comma-separated list of selected photo IDs',
                              required=True)
update_meta_data.add_argument('metadata_type', type=str,
                              help='Type of metadata to update (location or creation_date)', required=True)
update_meta_data.add_argument('metadata', type=str,
                              help='metadata is required', required=True)

users_for_permissions = reqparse.RequestParser()
users_for_permissions.add_argument('users', type=list, action="append", help='users is required', required=True)


class PhotoData(Resource):
    @jwt_required()
    def post(self, photo_id):
        user = get_user_by_id(get_jwt_identity())
        photo = Photo.query.filter_by(id=photo_id).first()
        permissions = Permission.query.filter_by(target_id=photo_id, target="photo").all()
        permissions_email = [permission.email for permission in permissions if permission.editable]
        args = request.get_json()

        title = args.get('title')
        description = args.get('description')
        location = args.get('location')
        creation_data = args.get('creation_time')

        if photo:
            if photo.user_id == user.id or user.email in permissions_email:

                if title:
                    photo.meta_data.title = title
                if description:
                    photo.meta_data.description = description
                if location:
                    photo.meta_data.location = location
                if creation_data:
                    photo.meta_data.creation_data = creation_data

                db.session.commit()
            else:
                return {'message': f'User {user.email} '
                                   f'does not have permissions to update photo meta data '}, 403
        else:
            return {'message': f'Photo id: {photo_id} does not exist'}, 404

        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200


class BatchPhotoData(Resource):
    @jwt_required()
    def post(self):
        user = get_user_by_id(get_jwt_identity())

        args = update_meta_data.parse_args()
        selected_photo = args.get('selected_photos')
        metadata_type = args.get('metadata_type')
        metadata = args.get('metadata')

        if metadata_type not in ('location', 'creation_date'):
            return {'error': 'metadata_type should be "location" or "creation_date"'}, 400
        for photo_id in selected_photo:
            photo = Photo.query.filter_by(id=photo_id).first()
            permissions = Permission.query.filter_by(target_id=photo_id, target="photo").all()
            permissions_email = [permission.email for permission in permissions if permission.editable]
            if photo:
                if photo.user_id == user.id or user.email in permissions_email:

                    if metadata_type == 'location':
                        photo.meta_data.location = metadata
                    elif metadata_type == 'creation_date':
                        photo.meta_data.creation_data = metadata
                    db.session.commit()
                else:
                    return {'message': f'User {user.email} '
                                       f'does not have permissions to update photo meta data '}, 403
            else:
                return {'message': f'Photo id: {photo_id} does not exist'}, 404
        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200


api.add_resource(PhotoData, '/api/v1/photo/<int:photo_id>')
api.add_resource(BatchPhotoData, '/api/v1/photo/batch')
api.add_resource(UserPhoto, '/api/v1/photo')
