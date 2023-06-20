from flask_sqlalchemy import SQLAlchemy
from flask_user import UserMixin

db = SQLAlchemy()


class Users(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(10), unique=True, nullable=True)
    parent_token = db.Column(db.String(10), nullable=True)
    parent_id = db.Column(db.Integer, nullable=True)

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
    service = db.Column(db.String(32), nullable=False)
    token = db.Column(db.String(300), nullable=True)
    refresh_token = db.Column(db.String(300), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    users = db.relationship('Users', secondary='editing_permission', backref='photos')

    def __repr__(self):
        return f'<Photo {self.id}>'


class EditingPermission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    photo_id = db.Column(db.Integer, db.ForeignKey('photos.id'), nullable=False)
    email = db.Column(db.String(225), db.ForeignKey('users.email'), nullable=False)
    editable = db.Column(db.Boolean, default=False)

