from src.auth.auth import auth, init_login_app, current_user
from src.oauth2.oauth2 import oauth2
from src.photos.photo_handler import photos
from src.app.config import *
from src.app.Forms import UpdateForm
from flask import *
from google.oauth2.credentials import Credentials
import requests
import google.oauth2.credentials
from src.photos.DBHandler import DBHandler
from src.app.model import db, Photos, PhotosMetaData, EditingPermission, Users

db_handler = DBHandler()


def create_app():
    app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), '..', '..', 'templates'),
                static_folder=os.path.join(os.path.dirname(__file__), '..', '..', 'static'))

    app.register_blueprint(photos, url_prefix='/photos')

    app.register_blueprint(auth, url_prefix='/auth')

    app.register_blueprint(oauth2, url_prefix='/oauth2')

    app.secret_key = SECRET_KEY

    app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config['USER_APP_NAME'] = 'Forever_app'
    app.config['USER_ENABLE_EMAIL'] = False
    app.config['USER_ENABLE_USERNAME'] = True
    app.config['USER_REQUIRE_RETYPE_PASSWORD'] = False

    app.config['MAIL_SERVER'] = STMP_SERVER
    app.config['MAIL_PORT'] = STMP_PORT
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = STMP_USERNAME  # Здесь указываете вашу почту
    app.config['MAIL_PASSWORD'] = STMP_PASSWORD  # Здесь указываете пароль от вашей почты

    db.init_app(app)
    with app.app_context():
        db.create_all()
    init_login_app(app)
    return app


app = create_app()


@app.route('/')
def user_photos():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        form = UpdateForm(request.form)
        current_user_family = Users.query.filter_by(parent_id=current_user.parent_id).all()
        photo_url = []
        family_users = []
        for family_user in current_user_family:
            family_user_photos = Photos.query.filter_by(user_id=family_user.id).all()
            correct_family_user_photos = []
            for photo in family_user_photos:
                photos_meta_data = PhotosMetaData.query.filter_by(photo_id=photo.id).first()
                if not photos_meta_data:
                    correct_family_user_photos.append(photo)
            photo_urls = db_handler.get_photos_from_db(correct_family_user_photos, session['credentials'])
            dict_photo_data = {family_user.email: photo_urls}
            family_users.append(family_user.email)
            photo_url.append(dict_photo_data)
        return render_template('photo_templates/user_photo.html', photos=photo_url,
                               parent_id=current_user.parent_id, family_users=family_users,
                               permissions=EditingPermission, form=form)
    else:
        return redirect(url_for('auth.login'))


@app.route('/session_clear')
def session_clear():
    session.clear()
    return redirect(url_for('index'))


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
    app.run(port=8080)
