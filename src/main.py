from src.auth.auth import http_auth, auth, init_app, current_user
from src.oauth2.oauth2 import oauth2, oauth2_init_app, check_credentials
from src.photos.photo_handler import photos, photos_init_app
from src.family_tree.family_tree import family_tree, family_tree_init_app
from src.face_recognition.people_face_recognition import people_face, face_recognition_init_app
from src.app.config import *
from src.app.Forms import UpdateForm, UpdateCreationDateForm, UpdateLocationForm
from flask import *
from flask_login import login_required
from google.oauth2.credentials import Credentials
import requests
import google.oauth2.credentials
from src.photos.DBHandler import DBHandler
from src.app.model import db, Photo, PhotoMetaData, EditingPermission, User
from src.app.init_celery import make_celery
from flask_restful import Api, Resource
from datetime import timedelta


db_handler = DBHandler()


def create_app():
    app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), '', '..', 'templates'),
                static_folder=os.path.join(os.path.dirname(__file__), '', '..', 'static'))

    app.register_blueprint(photos, url_prefix='/photos')

    app.register_blueprint(auth, url_prefix='/auth')

    app.register_blueprint(oauth2, url_prefix='/oauth2')

    app.register_blueprint(family_tree, url_prefix='/family_tree')

    app.register_blueprint(people_face, url_prefix='/people')

    app.secret_key = SECRET_KEY

    app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config['JWT_SECRET_KEY'] = 'furhfwuhuwfhfwuiwu83heuhdfuheufheuhfe'
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)

    app.config['USER_APP_NAME'] = 'Forever_app'
    app.config['USER_ENABLE_EMAIL'] = False
    app.config['USER_ENABLE_USERNAME'] = True
    app.config['USER_REQUIRE_RETYPE_PASSWORD'] = False

    app.config['MAIL_SERVER'] = STMP_SERVER
    app.config['MAIL_PORT'] = STMP_PORT
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = STMP_USERNAME  # Здесь указываете вашу почту
    app.config['MAIL_PASSWORD'] = STMP_PASSWORD

    app.config.update(
        CELERY_BROKER_URL=BROKER_URI,  # URL для подключения к Redis
        CELERY_RESULT_BACKEND='db+' + SQLALCHEMY_DATABASE_URI,  # URL для подключения к PostgreSQL
    )

    celery = make_celery(app)
    celery.set_default()

    db.init_app(app)
    with app.app_context():
        db.create_all()
    init_app(app)
    oauth2_init_app(app)
    photos_init_app(app)
    face_recognition_init_app(app)
    family_tree_init_app(app)
    return app, celery


app, celery = create_app()
app.app_context().push()
api = Api(app)


@app.route('/')
def user_photos():
    if current_user.is_authenticated:
        credentials = check_credentials()

        form = UpdateForm(request.form)
        location_form = UpdateLocationForm(request.form)
        creation_date_form = UpdateCreationDateForm(request.form)
        family_photos = Photo.query.filter(User.parent_id == current_user.parent_id, Photo.user_id == User.id).all()
        photo_urls = db_handler.get_photos_from_db(family_photos, credentials)
        current_user_family = User.query.filter_by(parent_id=current_user.parent_id).all()
        photo_data = {}
        family_users = []

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

            family_users.append(family_user.email)
        return render_template('photo_templates/user_photo.html', photos=photo_data,
                               parent_id=current_user.parent_id, family_users=family_users,
                               permissions=EditingPermission,
                               form=form, location_form=location_form, creation_date_form=creation_date_form)
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


if __name__ == '__main__':
    app.run()
