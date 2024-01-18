from flask import *
from datetime import timedelta
from flask_login import LoginManager
from flask_user import UserManager
from flask_mail import Mail
from flask_restful import Api
import os
def create_app():
    from src.app.config import (os, SECRET_KEY,
                                SQLALCHEMY_DATABASE_URI, STMP_SERVER, STMP_PORT, STMP_USERNAME,
                                STMP_PASSWORD, BROKER_URI)
    from src.auth.auth import auth
    from src.oauth2.oauth2 import oauth2
    from src.photos.photo_handler import photos
    from src.family_tree.family_tree import family_tree
    from src.face_recognition.people_face_recognition import people_face
    from src.photos.comment import comment
    from src.app.model import db, User
    from src.app.init_celery import make_celery

    app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), '', '..', 'templates'),
                static_folder=os.path.join(os.path.dirname(__file__), '', '..', 'static'))

    app.register_blueprint(photos, url_prefix='/photos')

    app.register_blueprint(auth, url_prefix='/auth')

    app.register_blueprint(oauth2, url_prefix='/oauth2')

    app.register_blueprint(family_tree, url_prefix='/family_tree')

    app.register_blueprint(people_face, url_prefix='/people')

    app.register_blueprint(comment, url_prefix='/comment')

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

    os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'

    app.config.update(
        CELERY_BROKER_URL=BROKER_URI,  # URL для подключения к Redis
        CELERY_RESULT_BACKEND='db+' + SQLALCHEMY_DATABASE_URI,  # URL для подключения к PostgreSQL
    )

    celery = make_celery(app)
    celery.set_default()

    db.init_app(app)

    with app.app_context():
        db.create_all()

    LoginManager(app)
    UserManager(app, db, User)
    mail = Mail(app)
    api = Api(app)

    return app, celery
