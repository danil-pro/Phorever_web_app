from flask_user import UserManager
from src.app.Forms import RegisterForm, LoginForm
from flask_login import LoginManager, login_user, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask import *
from src.app.model import db, User
from flask_mail import Mail, Message
import random
import string
from flask_restful import Api, Resource, reqparse
from flask_httpauth import HTTPBasicAuth
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager

auth = Blueprint('auth', __name__, template_folder='../templates/auth_templates', static_folder='../static')
login_manager = LoginManager()
http_auth = HTTPBasicAuth()
jwt = JWTManager()
# login_manager.login_view = "login"
mail = Mail()
api = Api()


def init_app(app):
    api.init_app(app)
    login_manager.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)
    UserManager(app, db, User)


def send_email(email, message, body):
    msg = Message(message, sender='phorever.cloud@gmail.com', recipients=[email])
    msg.body = body
    mail.send(msg)


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
        send_email(form.email.data, '', f'''Для подтверждения своей электронной почты, пожалуйста, посетите следующую ссылку:
    {url_for('auth.verify_email', email=form.email.data, token=new_user.verification_token, _external=True)}
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
                flash('Ваша электронная почта уже была подтверждена.')
                return redirect(url_for('index'))
            else:
                user.is_verified = True
                if user.parent_id is None:
                    user.parent_id = user.id
                db.session.add(user)
                db.session.commit()
                flash('Ваша электронная почта была успешно подтверждена.')
                return redirect(url_for('auth.login'))
        else:
            print('err')
    except:
        flash('Неверный токен верификации.')
        return redirect(url_for('auth.verify_email'))
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
                       f"{url_for('auth.register', parent_token=current_user.parent_token,  _external=True)}")
            flash('The invitation has been sent')
        return render_template('auth_templates/profile.html')
    else:
        return redirect(url_for('auth.login'))


create_user = reqparse.RequestParser()
create_user.add_argument("email", type=str, help="User email is required", required=True)
create_user.add_argument("password", type=str, help="User password is required", required=True)
create_user.add_argument("confirm_password", type=str, help="User password is required", required=True)
create_user.add_argument("invite_token", type=str, help="User parent token")


class SingUp(Resource):
    def post(self):
        args = create_user.parse_args()
        password = generate_password_hash(args.get('password'))
        user = User.query.filter_by(email=args.get('email')).first()
        if user:
            return {'message': 'User exist'}, 409
        if args.get('password') != args.get('confirm_password'):
            return {'message': 'Password mismatch'}, 401
        new_user = User(email=args.get('email'), password=password)
        new_user.verification_token = str(random.randint(100000, 999999))
        parent_token = args.get('invite_token')
        if parent_token is None:
            new_user.parent_id = None
        else:
            parent_user = User.query.filter_by(parent_token=parent_token).first()
            if not parent_user:
                return {'message': 'The user who invited does not exist'}, 404
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
        send_email(args.get('email'), '', f'''Для подтверждения своей электронной почты, пожалуйста, посетите следующую ссылку:
        {url_for('auth.verify_email', email=args.get('email'), token=new_user.verification_token, _external=True)}
        Если вы не запрашивали подтверждение своей электронной почты, то просто проигнорируйте это сообщение.
        ''')
        return {'success': True, 'data': {'user': new_user.email, 'code': 200, 'message': 'OK'}}, 200


user_login = reqparse.RequestParser()
user_login.add_argument("email", type=str, help="User email is required", required=True)
user_login.add_argument("password", type=str, help="User password is required", required=True)


class SingIn(Resource):
    def get(self):
        args = user_login.parse_args()
        email = args.get('email')
        password = args.get('password')
        user = load_user(email)
        if not user:
            return {'message': 'User not found'}, 404

        if user and not user.is_verified:
            return {'message': 'Email is not verified'}, 403

        if user.password and check_password_hash(user.password, password):

            access_token = create_access_token(identity=user.id)
            return {'success': True, 'data': {'user': user.email, 'access_token': access_token,
                                              'code': 200, 'message': 'OK'}}, 200
        else:
            return {'message': 'Incorrect email or password'}, 401


api.add_resource(SingUp, '/api/v1/auth/sing_up')
api.add_resource(SingIn, '/api/v1/auth/sing_in')

