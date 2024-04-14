import random
import string

from flask import *
from flask_jwt_extended import create_access_token
from flask_login import LoginManager, login_user, current_user, logout_user
from flask_mail import Mail
from flask_restful import Api, Resource
from marshmallow import ValidationError
from werkzeug.security import generate_password_hash, check_password_hash

from src.app.Forms import RegisterForm, LoginForm
from src.app.model import db, User
from src.app.utils import send_email
from src.auth.UserAuth import UserSchema, LoginSchema

auth = Blueprint('auth', __name__, template_folder='../templates/auth_templates', static_folder='../static')

login_manager = LoginManager()

mail = Mail()

api = Api()


def auth_init_app(app):
    api.init_app(app)


@login_manager.user_loader
def load_user(email):
    print('ok')
    return User.query.filter_by(email=email).first()


@auth.route('/register/<parent_token>', methods=['GET', 'POST'])
@auth.route('/register', methods=['GET', 'POST'])
def register(parent_token=None):
    if current_user.is_authenticated:
        return redirect(url_for('auth.profile'))
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        password = generate_password_hash(form.password.data)
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            flash('Пользователь с таким адресом электронной почты уже зарегистрирован.')
            return redirect(url_for('auth.register'))
        new_user = User(email=form.email.data, password=password)
        new_user.verification_token = str(random.randint(100000, 999999))
        parent_token = request.form.get('parent_token')
        if parent_token == 'None':
            new_user.parent_id = None
        else:
            parent_user = User.query.filter_by(parent_token=parent_token).first()
            if not parent_user:
                flash('The user who invited you does not exist')
                return redirect(url_for('auth.register'))
            if parent_user.parent_id:
                new_user.parent_id = parent_user.parent_id
            else:
                new_user.parent_id = parent_user.id
        new_user.parent_token = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        new_user.token = None
        new_user.refresh_token = None
        new_user.apple_id = None
        db.session.add(new_user)
        db.session.commit()
        send_email(form.email.data, '', f'''Для подтверждения своей электронной почты, пожалуйста, посетите следующую 
        ссылку: {url_for('auth.verify_email', email=form.email.data, token=new_user.verification_token, _external=True)}
    Если вы не запрашивали подтверждение своей электронной почты, то просто проигнорируйте это сообщение.
    ''')
        return render_template('auth_templates/verification.html')
    return render_template('auth_templates/register.html', form=form, parent_token=parent_token)


@auth.route('/verify-email/<email>/<token>', methods=['GET', 'POST'])
def verify_email(email, token):
    try:
        user = load_user(email)
        verification_code = user.verification_token
        if token == verification_code:
            if user and user.is_verified:
                flash('Your email has already been confirmed.')
                return redirect(url_for('auth.login'))
            else:
                user.is_verified = True
                if user.parent_id is None:
                    user.parent_id = user.id
                db.session.add(user)
                db.session.commit()
                flash('Your email has been successfully verified.')
                return redirect(url_for('auth.login'))
        else:
            print('err')
    except Exception as e:
        flash('Invalid verification token.')
        return redirect(url_for('auth.login'))
    return redirect(url_for('auth.login'))


@auth.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if request.method == 'POST' and form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        user = load_user(email)
        if not user:
            flash('no user', 'info')
            return render_template('auth_templates/login.html', form=form)
        elif user.password and check_password_hash(user.password, password):
            login_user(user)
            current_user.is_authenticated = True
            return redirect(request.args.get('next') or url_for('user_photos'))
        elif user and not user.is_verified:
            flash('Ваша электронная почта не была подтверждена. Проверьте свою почту и следуйте ин'
                  'струкциям, чтобы завершить регистрацию.')
            return redirect(url_for('auth.login'))
        else:
            flash('Invalid username or password')
    return render_template('auth_templates/login.html', form=form)


@auth.route('/logout')
def logout():
    if current_user.is_authenticated:
        logout_user()

    return redirect(url_for('auth.login'))


@auth.route('/profile', methods=['GET', 'POST'])
def profile():
    if current_user.is_authenticated:
        if request.method == 'POST':
            invite = request.form['invite']
            send_email(invite, f'Invite to Phorever from {current_user.email}',
                       f"{url_for('auth.register', parent_token=current_user.parent_token, _external=True)}")
            flash('The invitation has been sent')
        return render_template('auth_templates/profile.html')
    else:
        return redirect(url_for('auth.login'))


class SignUp(Resource):
    def post(self):
        user_schema = UserSchema()
        try:
            # Загрузка и валидация данных запроса
            user = user_schema.load(request.json)
        except ValidationError as err:
            # Возвращение ошибки, если данные невалидны
            return {"errors": err.messages}, 400

        # Если данные валидны, user уже создан и сохранен в базе данных в post_load
        return {'success': True, 'data': {'user': user.email, 'code': 200, 'message': 'OK'}}, 200


class SignIn(Resource):
    def post(self):
        login_schema = LoginSchema()
        try:
            # Загрузка и валидация данных запроса
            user = login_schema.load(request.json)
        except ValidationError as err:
            # Возвращение ошибки, если данные невалидны
            return {"errors": err.messages}, 400
        access_token = create_access_token(identity=user.id)
        # Если данные валидны, user уже создан и сохранен в базе данных в post_load
        return {'success': True, 'data': {'user': user.email, 'access_token': access_token,
                                          'code': 200, 'message': 'OK'}}, 200


api.add_resource(SignUp, '/api/v1/auth/sign_up')
api.add_resource(SignIn, '/api/v1/auth/sign_in')
