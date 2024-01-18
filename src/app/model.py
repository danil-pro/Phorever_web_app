from flask_sqlalchemy import SQLAlchemy
from flask_user import UserMixin
from datetime import datetime
import keyring
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
    parent_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    family = db.relationship('User', backref=db.backref('parent', remote_side=[id]))
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


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Добавлено
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'))

    photo = db.relationship('Photo', foreign_keys=[photo_id], backref='photo')
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='received_messages')


class UserMessage(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), primary_key=True)

    user = db.relationship('User', backref='user_messages')
    message = db.relationship('Message', backref='user_messages')



