from flask_user import UserManager
from Forms import RegisterForm, LoginForm
from flask_login import LoginManager, login_user, current_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from flask import *
from model import db, Users
from flask_mail import Mail, Message
import random

auth = Blueprint('auth', __name__, template_folder='../templates', static_folder='../static')

login_manager = LoginManager()
mail = Mail()


def init_login_app(app):
    login_manager.init_app(app)
    mail.init_app(app)
    UserManager(app, db, Users)


def send_verification_email(email):
    user = load_user(email)
    msg = Message('Verification Code', sender='danishevchuk@gmail.com', recipients=[email])
    msg.body = f'Your verification code is: {user.verification_token}'
    mail.send(msg)
    # verification_url = url_for('auth.verify_email', email=email, _external=True)


@login_manager.user_loader
def load_user(email):
    print('ok')
    return Users.query.filter_by(email=email).first()


@auth.route('/register', methods=['GET', 'POST'])
def register():
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
        db.session.add(new_user)
        db.session.commit()
        send_verification_email(form.email.data)
        return redirect(url_for('auth.verify_email', email=form.email.data))
    return render_template('register.html', form=form)


@auth.route('/verify-email/<email>', methods=['GET', 'POST'])
def verify_email(email):
    try:
        if request.method == 'POST':
            user = load_user(email)
            entered_code = request.form['verification_code']
            verification_code = user.verification_token
            if entered_code == verification_code:
                if user and user.is_verified:
                    flash('Ваша электронная почта уже была подтверждена.')
                else:
                    user.is_verified = True
                    db.session.add(user)
                    db.session.commit()
                    flash('Ваша электронная почта была успешно подтверждена.')
                    return redirect(url_for('auth.login'))
            else:
                print('err')
    except:
        flash('Неверный токен верификации.')
        return redirect(url_for('auth.verify_email'))
    return render_template('verification.html', email=email)


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
        session.clear()
        if 'credentials' in session:
            del session['credentials']
        if 'access_token' in session:
            del session['access_token']
    return redirect(url_for('auth.login'))


@auth.route('/profile')
def profile():
    if current_user.is_authenticated:
        return render_template('profile.html')
    else:
        return redirect(url_for('auth.login'))


# if __name__ == '__main__':
#     app.run()
