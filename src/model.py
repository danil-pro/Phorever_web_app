from flask_sqlalchemy import SQLAlchemy
from flask_user import UserMixin

db = SQLAlchemy()


class Users(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100), unique=True, nullable=True)

    def __init__(self, email, password):
        self.email = email
        self.password = password

    def is_authenticated(self):
        return hasattr(self, 'is_verified') and self.is_authenticated


class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(200000), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    def __repr__(self):
        return f'<Photo {self.url}>'
