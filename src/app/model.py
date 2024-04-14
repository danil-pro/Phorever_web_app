from flask_sqlalchemy import SQLAlchemy
from flask_user import UserMixin
from datetime import datetime


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
    google_token = db.Column(db.String(255), nullable=True)
    google_refresh_token = db.Column(db.String(255), nullable=True)
    google_credentials_create_at = db.Column(db.BigInteger, nullable=True)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'))
    person = db.relationship('Person', backref='user', uselist=False)
    note = db.relationship('Note', back_populates='author')

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


class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    photo_data = db.Column(db.String(200000), nullable=False)
    photo_url = db.Column(db.String(200000), nullable=False)
    service = db.Column(db.String(32), nullable=False)
    token = db.Column(db.String(300), nullable=True)
    refresh_token = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default='2023-07-13 15:30:45.123456', nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='photo_owner')
    meta_data = db.relationship('PhotoMetaData', backref='meta_data', uselist=False)

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


class Permission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    target = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)

    email = db.Column(db.String(225), db.ForeignKey('user.email'), nullable=False)
    editable = db.Column(db.Boolean, default=False)


class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    birth_date = db.Column(db.BigInteger, nullable=True)
    death_date = db.Column(db.BigInteger, nullable=True)
    birth_place = db.Column(db.String(50), nullable=True)

    note = db.relationship('Note', back_populates='person')
    face_code = db.Column(db.String(6), db.ForeignKey('face_encode.face_code'), nullable=False)
    face_encode = db.relationship('FaceEncode', backref='person', uselist=True)
    bio = db.relationship('Bio', backref='person', uselist=True)


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    note = db.Column(db.String(500), nullable=False)
    date = db.Column(db.BigInteger, nullable=False)
    author = db.relationship('User', back_populates='note')
    person = db.relationship('Person', back_populates='note')


class UserPerson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    relative_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)
    relationship_type = db.Column(db.String(50), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)
    person_type = db.Column(db.String(50), nullable=False)
    degree = db.Column(db.String(50), nullable=True)
    line = db.Column(db.String(50), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    author = db.relationship('User', backref='user_person')
    relative_person = db.relationship('Person', foreign_keys=[relative_id], backref='relative_person')
    person = db.relationship('Person', foreign_keys=[person_id], backref='person')


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user_messages = db.relationship('UserMessage', back_populates='message')

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='received_messages')


class UserMessage(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), primary_key=True)
    timestamp = db.Column(db.BigInteger, index=True, default=lambda: int(datetime.utcnow().timestamp()))
    content = db.Column(db.Text, nullable=False)
    target_id = db.Column(db.Integer, nullable=True)
    target_type = db.Column(db.String(50), nullable=True)

    user = db.relationship('User', backref='user_messages')
    message = db.relationship('Message', back_populates='user_messages')


class Bio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event = db.Column(db.String(50), nullable=False)
    text_content = db.Column(db.String(500), nullable=False)
    photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'), nullable=True)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)
