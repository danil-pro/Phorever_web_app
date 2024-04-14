from src.oauth2.oauth2 import check_credentials
from src.app.Forms import UpdateCreationDateForm, UpdateLocationForm
from flask_login import current_user
from flask import *
from google.oauth2.credentials import Credentials
import requests
import google.oauth2.credentials
from src.photos.DBHandler import DBHandler
from src.app.model import Photo, PhotoMetaData, Permission, User
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

        current_user_family = User.query.filter_by(parent_id=current_user.parent_id).all()
        photo_data = []

        # Iterate over family photos to build photo metadata
        for photo in family_photos:
            photo_data.append({
                'baseUrl': photo.photo_url,
                'title': photo.meta_data.title if photo.meta_data.title else 'Empty',
                'description': photo.meta_data.description if photo.meta_data.description else 'Empty',
                'location': photo.meta_data.location if photo.meta_data.location else 'Empty',
                'creation_data': photo.meta_data.creation_data if photo.meta_data.creation_data else 'Empty',
                'photo_id': photo.id,
                'photo_owner': photo.user.email

            })

        return render_template('photo_templates/user_photo.html', photos=photo_data,
                               parent_id=current_user.parent_id, permissions=Permission,
                               location_form=location_form, creation_date_form=creation_date_form)
    else:
        return redirect(url_for('auth.login'))


# @app.route('/session_clear')
# def session_clear():
#     session.clear()
#     return redirect(url_for('user_photos'))
#
#
# @app.route('/googleb3f997e5d55f0443.html')
# def google_verif():
#     return render_template('googleb3f997e5d55f0443.html')


@app.route('/privacy')
def privacy():
    return redirect('https://phorever.cloud/privacy')


@app.route('/eula')
def eula():
    return redirect('https://phorever.cloud/eula')


@app.route('/robot.txt')
def static_from_root():
    return send_from_directory(app.static_folder, 'robot.txt')


# @app.route('/revoke')
# def revoke():
#     if 'credentials' not in session:
#         return ('You need to <a href="/authorize">authorize</a> before ' +
#                 'testing the code to revoke credentials')
#     credentials = google.oauth2.credentials.Credentials(
#         **session['credentials'])
#
#     revoke = requests.post(REVOKE_TOKEN,
#                            params={'token': credentials.token},
#                            headers={'content-type': 'application/x-www-form-urlencoded'})
#
#     status_code = getattr(revoke, 'status_code')
#     if status_code == 200:
#         return 'Credentials successfully revoked.'
#     else:
#         return 'An error occurred.' + str(status_code) + str(session['credentials'])


# @app.route('/test')
# def test():
#     return render_template('photo_templates/../templates/person_template/bio.html')
