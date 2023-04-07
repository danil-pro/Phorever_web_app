from flask_user import UserManager
from src.Forms import RegisterForm, LoginForm
# from config import *
from flask_login import LoginManager, login_user
# from UserLogin import UserLogin
from werkzeug.security import generate_password_hash, check_password_hash
from src.url_photos_getters import photos
from src.config import SECRET_KEY
from flask import *
from flask_migrate import Migrate
from src.model import db, Users
# from UserLogin import UserLogin


app = Flask(__name__, template_folder='../templates')

app.register_blueprint(photos, url_prefix='/photos')

app.secret_key = SECRET_KEY

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:babyb00m@localhost:8080/postgres'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config['USER_APP_NAME'] = 'Forever_app'
app.config['USER_ENABLE_EMAIL'] = False  # Разрешение регистрации только через логин
app.config['USER_ENABLE_USERNAME'] = True  # Разрешение использования логина для аутентификации
app.config['USER_REQUIRE_RETYPE_PASSWORD'] = False
db.init_app(app)
user_manager = UserManager(app, db, Users)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(email):
    print('ok')
    return Users.query.filter_by(email=email).first()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        password = generate_password_hash(form.password.data)
        user = Users(email=form.email.data, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if request.method == 'POST' and form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        user = load_user(email)
        if not user:
            flash('no user', 'info')
            return render_template('login.html', form=form)
        elif user and check_password_hash(user.password, password):
            login_user(user)
            session['authenticated'] = True
            return redirect(request.args.get('next') or url_for('index'))
        else:
            flash('Invalid username or password')
    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    if session['authenticated']:
        session['authenticated'] = False
    if 'credentials' in session:
        del session['credentials']
    if 'access_token' in session:
        del session['access_token']
    return redirect(url_for('login'))


@app.route('/profile')
def profile():
    if session['authenticated']:
        return render_template('profile.html')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run()
