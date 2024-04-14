import random
import string
from src.app.model import FaceEncode, User
from flask_mail import Mail, Message

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

