from flask_sqlalchemy import SQLAlchemy
from flask_user import UserMixin
from datetime import datetime

db = SQLAlchemy()


class Users(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(10), unique=True, nullable=True)
    parent_token = db.Column(db.String(10), nullable=True)
    parent_id = db.Column(db.Integer, nullable=True)
    apple_id = db.Column(db.String(256), nullable=True)

    def __init__(self, email, password):
        self.email = email
        self.password = password

    def is_authenticated(self):
        return hasattr(self, 'is_verified') and self.is_authenticated


class PhotosMetaData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=True)
    description = db.Column(db.String(10000), nullable=True)
    location = db.Column(db.String(100), nullable=True)
    creation_data = db.Column(db.String(12), nullable=True)
    photo_id = db.Column(db.Integer, db.ForeignKey('photos.id'), nullable=False)
    photo = db.relationship('Photos', backref='metadata')


class Photos(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    photos_data = db.Column(db.String(200000), nullable=False)
    photos_url = db.Column(db.String(200000), nullable=False)
    service = db.Column(db.String(32), nullable=False)
    token = db.Column(db.String(300), nullable=True)
    refresh_token = db.Column(db.String(300), nullable=True)
    apple_id = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default='2023-07-13 15:30:45.123456', nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    users = db.relationship('Users', secondary='editing_permission', backref='photos')

    def __repr__(self):
        return f'<Photo {self.id}>'


class FaceEncode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    face_encode = db.Column(db.LargeBinary, nullable=True)
    photo_id = db.Column(db.Integer, db.ForeignKey('photos.id'), nullable=False)
    face_code = db.Column(db.String(6), nullable=False, unique=True)
    key_face = db.Column(db.String(6), nullable=True)
    not_a_key = db.Column(db.Boolean, default=False)
    photo = db.relationship('Photos', backref='face_encode')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


class EditingPermission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    photo_id = db.Column(db.Integer, db.ForeignKey('photos.id'), nullable=False)
    email = db.Column(db.String(225), db.ForeignKey('users.email'), nullable=False)
    editable = db.Column(db.Boolean, default=False)


class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=True)
    face_code = db.Column(db.String(6), db.ForeignKey('face_encode.face_code'), nullable=False)

    face_encode = db.relationship('FaceEncode', backref='person', uselist=False)


class Relationship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    relative_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)
    relationship_type = db.Column(db.String(50), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)
    person_type = db.Column(db.String(50), nullable=False)
    degree = db.Column(db.String(50), nullable=True)
    line = db.Column(db.String(50), nullable=True)


