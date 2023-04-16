from src.auth import auth, init_login_app
from src.url_photos_getters import photos
from src.config import *
from flask import *
from src.model import db
from google.oauth2.credentials import Credentials
import requests
import google.oauth2.credentials


def create_app():
    app = Flask(__name__, template_folder='../templates')

    app.register_blueprint(photos, url_prefix='/photos')

    app.register_blueprint(auth, url_prefix='/auth')

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

    init_login_app(app)
    # user = Users.query.first()
    # if user is not None:
    #     user_password = '' if user_manager.USER_ENABLE_AUTH0 else user.password[-8:]
    # UserManager(app, db, Users)
    # migrate = Migrate(app, db)

    return app


app = create_app()


@app.route('/')
def index():
    return render_template('index.html')


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
        return 'An error occurred.' + str(status_code)


if __name__ == '__main__':
    db.create_all()
    app.run()
