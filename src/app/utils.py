import random
import string
from functools import wraps
from src.app.model import FaceEncode, User, Person
from flask_mail import Mail, Message
from flask import jsonify
from flask_jwt_extended import get_jwt_identity
import json

mail = Mail()


def generate_unique_code():
    from run import app
    with app.app_context():  # Используйте контекст приложения
        while True:
            code = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
            if not FaceEncode.query.filter_by(face_code=code).first():
                return code


def send_email(email, message, body):
    msg = Message(message, sender='phorever.cloud@gmail.com', recipients=[email])
    msg.html = body
    mail.send(msg)


def get_user_by_id(user_id):
    return User.query.filter_by(id=user_id).first()


def check_access(model, target_id, user_id):
    resource = model.query.filter_by(id=target_id).first()
    if not resource:
        return jsonify({'error': 'Resource not found'}), 404

    user = get_user_by_id(user_id)

    if user.parent_id != resource.face_encode.parent_id:
        return jsonify({'error': 'Access denied'}), 403


def family_access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user_id = get_jwt_identity()  # Получаем ID текущего пользователя из JWT
        current_user = User.query.get(current_user_id)
        if not current_user:
            return {'message': 'User not found'}, 404

        person = Person.query.filter_by(face_code=kwargs['face_code']).first()
        if not person:
            return {'message': 'Person not found'}, 404

        if current_user.parent_id != person.parent_id:
            return {'message': 'Access denied'}, 403

        return f(*args, **kwargs)

    return decorated_function
