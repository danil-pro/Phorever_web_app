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
    token = db.Column(db.String(300), nullable=True)
    refresh_token = db.Column(db.String(300), nullable=True)

    def __init__(self, email, password):
        self.email = email
        self.password = password

    def is_authenticated(self):
        return hasattr(self, 'is_verified') and self.is_authenticated


# class Albums(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     album_id = db.Column(db.String(100), nullable=False)
#     user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


class Photos(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    photos_data = db.Column(db.String(200000), nullable=False)
    service = db.Column(db.String(32), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    def __repr__(self):
        return f'<Photo {self.id}>'
