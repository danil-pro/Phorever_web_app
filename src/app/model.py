from flask_sqlalchemy import SQLAlchemy
from flask_user import UserMixin
from datetime import datetime
from passlib.apps import custom_app_context as pwd_context
import jwt
import time
import keyring
from src.auth.auth import current_user
from flask import redirect, url_for
from pyicloud import PyiCloudService

db = SQLAlchemy()


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(10), unique=True, nullable=True)
    parent_token = db.Column(db.String(10), nullable=True)
    state = db.Column(db.String(225), nullable=True)
    parent_id = db.Column(db.Integer, nullable=True)
    apple_id = db.Column(db.String(225), nullable=True)
    google_token = db.Column(db.String(255), nullable=True)
    google_refresh_token = db.Column(db.String(255), nullable=True)
    google_credentials_create_at = db.Column(db.BigInteger, nullable=True)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'))
    person = db.relationship('Person', backref='user', uselist=False)

    def __init__(self, email, password):
        self.email = email
        self.password = password

    def is_authenticated(self):
        return hasattr(self, 'is_verified') and self.is_authenticated

    def icloud_api(self, code=None):
        from src.app.config import BASE
        if not self.apple_id:
            if not current_user:
                return {'icloud_uri': f"{BASE}/api/v1/icloud/auth"}
            else:
                return redirect(url_for('oauth2.icloud_authorize'))
        icloud_password = keyring.get_password("pyicloud", self.apple_id)
        if not icloud_password:
            return {'icloud_uri': f"{BASE}/api/v1/icloud/auth"}
        api = PyiCloudService(self.apple_id, icloud_password)
        api.authenticate(force_refresh=True)
        if code:
            result = api.validate_2fa_code(code)
            if not result:
                return {'message': 'Invalid verification code'}
        else:
            if api.requires_2fa:
                return {'icloud_uri': f"{BASE}/api/v1/icloud/auth/verify_2fa"}

        return api


class PhotoMetaData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=True)
    description = db.Column(db.String(10000), nullable=True)
    location = db.Column(db.String(100), nullable=True)
    creation_data = db.Column(db.BigInteger, nullable=True)
    photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'), nullable=False)
    photo = db.relationship('Photo', backref='metadata')


class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    photos_data = db.Column(db.String(200000), nullable=False)
    photos_url = db.Column(db.String(200000), nullable=False)
    video = db.Column(db.Boolean, default=False)
    service = db.Column(db.String(32), nullable=False)
    token = db.Column(db.String(300), nullable=True)
    refresh_token = db.Column(db.String(300), nullable=True)
    apple_id = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default='2023-07-13 15:30:45.123456', nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    users = db.relationship('User', secondary='editing_permission', backref='photo')

    def __repr__(self):
        return f'<Photo {self.id}>'


class FaceEncode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    face_encode = db.Column(db.LargeBinary, nullable=True)
    photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'), nullable=False)
    face_code = db.Column(db.String(6), nullable=False, unique=True)
    key_face = db.Column(db.String(6), nullable=True)
    not_a_key = db.Column(db.Boolean, default=False)
    photo = db.relationship('Photo', backref='face_encode')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class EditingPermission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'), nullable=False)
    email = db.Column(db.String(225), db.ForeignKey('user.email'), nullable=False)
    editable = db.Column(db.Boolean, default=False)


class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    birth_date = db.Column(db.BigInteger, nullable=True)
    death_date = db.Column(db.BigInteger, nullable=True)
    birth_place = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.JSON, nullable=True)
    face_code = db.Column(db.String(6), db.ForeignKey('face_encode.face_code'), nullable=False)

    face_encode = db.relationship('FaceEncode', backref='person', uselist=True)


class UserPerson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    relative_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)
    relationship_type = db.Column(db.String(50), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)
    person_type = db.Column(db.String(50), nullable=False)
    degree = db.Column(db.String(50), nullable=True)
    line = db.Column(db.String(50), nullable=True)


