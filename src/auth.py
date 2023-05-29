from flask_user import UserManager
from Forms import RegisterForm, LoginForm
from flask_login import LoginManager, login_user, current_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from flask import *
from model import db, Users
from flask_mail import Mail, Message
import random
import string
import requests

auth = Blueprint('auth', __name__, template_folder='../templates', static_folder='../static')

login_manager = LoginManager()
mail = Mail()


def init_login_app(app):
    login_manager.init_app(app)
    mail.init_app(app)
    UserManager(app, db, Users)


def send_email(email, message, body):
    msg = Message(message, sender='danishevchuk@gmail.com', recipients=[email])
    msg.body = body
    mail.send(msg)


@login_manager.user_loader
def load_user(email):
    print('ok')
    return Users.query.filter_by(email=email).first()


@auth.route('/register/<parent_token>', methods=['GET', 'POST'])
@auth.route('/register', methods=['GET', 'POST'])
def register(parent_token=None):
    if current_user.is_authenticated:
        return redirect(url_for('auth.profile'))
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        password = generate_password_hash(form.password.data)
        user = Users.query.filter_by(email=form.email.data).first()
        if user:
            flash('Пользователь с таким адресом электронной почты уже зарегистрирован.')
            return redirect(url_for('auth.register'))
        new_user = Users(email=form.email.data, password=password)
        new_user.verification_token = str(random.randint(100000, 999999))
        parent_token = request.form.get('parent_token')
        if parent_token == 'None':
            new_user.parent_id = None
        else:
            parent_user = Users.query.filter_by(parent_token=parent_token).first()
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
        db.session.add(new_user)
        db.session.commit()
        send_email(form.email.data, '', f'''Для подтверждения своей электронной почты, пожалуйста, посетите следующую ссылку:
    {url_for('auth.verify_email', email=form.email.data, token=new_user.verification_token, _external=True)}
    Если вы не запрашивали подтверждение своей электронной почты, то просто проигнорируйте это сообщение.
    ''')
        return render_template('verification.html')
    return render_template('register.html', form=form, parent_token=parent_token)


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
    print(current_user.is_authenticated)
    if request.method == 'POST' and form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        user = load_user(email)
        if not user:
            flash('no user', 'info')
            return render_template('login.html', form=form)
        elif user.password and check_password_hash(user.password, password):
            login_user(user)
            current_user.is_authenticated = True
            return redirect(request.args.get('next') or url_for('index'))
        elif user and not user.is_verified:
            flash('Ваша электронная почта не была подтверждена. Проверьте свою почту и следуйте ин'
                  'струкциям, чтобы завершить регистрацию.')
            return redirect(url_for('auth.login'))
        else:
            flash('Invalid username or password')
    return render_template('login.html', form=form)


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
        return render_template('profile.html')
    else:
        return redirect(url_for('auth.login'))

# if __name__ == '__main__':
#     app.run()
