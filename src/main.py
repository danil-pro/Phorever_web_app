from src.oauth2.oauth2 import check_credentials
from src.app.Forms import UpdateCreationDateForm, UpdateLocationForm
from flask_login import current_user
from flask import *
from google.oauth2.credentials import Credentials
import requests
import google.oauth2.credentials
from src.photos.DBHandler import DBHandler
from src.app.model import Photo, PhotoMetaData, EditingPermission, User
from src.app.config import *
from run import app


db_handler = DBHandler()


@app.route('/')
def user_photos():
    if current_user.is_authenticated:
        credentials = check_credentials()

        location_form = UpdateLocationForm(request.form)
        creation_date_form = UpdateCreationDateForm(request.form)
        family_photos = Photo.query.filter(User.parent_id == current_user.parent_id, Photo.user_id == User.id).all()
        photo_urls = db_handler.get_photos_from_db(family_photos, credentials)

        current_user_family = User.query.filter_by(parent_id=current_user.parent_id).all()
        photo_data = {}

        for family_user in current_user_family:
            # print(family_user.email)
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

        return render_template('photo_templates/user_photo.html', photos=photo_data,
                               parent_id=current_user.parent_id, permissions=EditingPermission,
                               location_form=location_form, creation_date_form=creation_date_form)
    else:
        return redirect(url_for('auth.login'))


@app.route('/session_clear')
def session_clear():
    session.clear()
    return redirect(url_for('user_photos'))


@app.route('/googleb3f997e5d55f0443.html')
def google_verif():
    return render_template('googleb3f997e5d55f0443.html')


@app.route('/privacy')
def privacy():
    return redirect('https://phorever.cloud/privacy')


@app.route('/eula')
def eula():
    return redirect('https://phorever.cloud/eula')


@app.route('/robot.txt')
def static_from_root():
    return send_from_directory(app.static_folder, 'robot.txt')


@app.route('/revoke')
def revoke():
    if 'credentials' not in session:
        return ('You need to <a href="/authorize">authorize</a> before ' +
                'testing the code to revoke credentials')
    credentials = google.oauth2.credentials.Credentials(
        **session['credentials'])

    revoke = requests.post(REVOKE_TOKEN,
                           params={'token': credentials.token},
                           headers={'content-type': 'application/x-www-form-urlencoded'})

    status_code = getattr(revoke, 'status_code')
    if status_code == 200:
        return 'Credentials successfully revoked.'
    else:
        return 'An error occurred.' + str(status_code) + str(session['credentials'])

