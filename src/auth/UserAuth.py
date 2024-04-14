from marshmallow import Schema, fields, validate, validates_schema, validates, ValidationError, post_load
from werkzeug.security import generate_password_hash, check_password_hash
import random, string
from src.app.model import User, db
from flask import render_template, url_for
from src.app.utils import send_email



class UserSchema(Schema):
    email = fields.Email(required=True, error_messages={"required": "User email is required"})
    password = fields.Str(required=True, validate=validate.Length(min=8), error_messages={"required": "User password "
                                                                                                      "is required"})
    confirm_password = fields.Str(required=True)
    invite_token = fields.Str(load_default=None)

    @validates('email')
    def validate_email(self, value, **kwargs):
        if User.query.filter_by(email=value).first():
            raise ValidationError('User with this email already exists.')

    @validates_schema
    def validate_passwords_match(self, data, **kwargs):
        if data['password'] != data.get('confirm_password'):
            raise ValidationError('Passwords do not match.')

    @post_load
    def create_user(self, data, **kwargs):
        user = User(
            email=data['email'],
            password=generate_password_hash(data['password'])
        )
        user.verification_token = str(random.randint(100000, 999999))

        if data['invite_token']:
            parent_user = User.query.filter_by(parent_token=data['invite_token']).first()
            if not parent_user:
                raise ValidationError('The user who invited does not exist.')
            user.parent_id = parent_user.id if not parent_user.parent_id else parent_user.parent_id

        user.parent_token = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        db.session.add(user)
        db.session.commit()

        # Здесь должна быть ваша логика отправки электронного письма для верификации
        verification_url = url_for('auth.verify_email', email=user.email, token=user.verification_token, _external=True)
        email_body = render_template('emails/auth/email_verification.html', verification_url=verification_url)
        send_email(user.email, "Email Verification", email_body)

        return user


class LoginSchema(Schema):
    email = fields.Email(required=True, error_messages={"required": "User email is required"})
    password = fields.Str(required=True, validate=[validate.Length(min=6)],
                          error_messages={"required": "User password is required"})

    @post_load
    def validate_credentials(self, data, **kwargs):
        user = User.query.filter_by(email=data['email']).first()
        if not user or not check_password_hash(user.password, data['password']):
            raise ValidationError('Invalid email or password.', 'password')
        if not user.is_verified:
            raise ValidationError('Email is not verified', 'password')

        return user
