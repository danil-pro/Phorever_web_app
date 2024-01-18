import os
import flask
from flask import *
from flask_login import current_user
from src.app.config import *

from google_auth_oauthlib.flow import Flow

from src.oauth2.Oauth2_Connector import GoogleOauth2Connect, DropboxOauth2Connect
from src.app.Forms import IcloudLoginForm, VerifyVerificationCodeForm, ICloudVerifyForm
from src.app.model import User, db
from flask_restful import Api, Resource, reqparse

from flask_jwt_extended import jwt_required, get_jwt_identity

import keyring
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException

oauth2 = Blueprint('oauth2', __name__, template_folder='../templates', static_folder='../static')
current_dir = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS_FILE = CLIENT_SECRETS_FILE

absolute_path = os.path.join(current_dir, CLIENT_SECRETS_FILE)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

api = Api()
SCOPES = [SCOPE1, SCOPE2, SCOPE3]
API_SERVICE_NAME = API_SERVICE_NAME
API_VERSION = API_VERSION
GOOGLE_REDIRECT_URI = GOOGLE_REDIRECT_URI
google_auth = GoogleOauth2Connect(CLIENT_SECRETS_FILE, SCOPES, API_SERVICE_NAME, API_VERSION)


authenticator = DropboxOauth2Connect(
    app_key=APP_KEY,
    app_secret=APP_SECRET,
    redirect_uri=DROPBOX_REDIRECT_URI,
    session=session
)


@oauth2.route('/google_authorize')
# @jwt_required()
def google_authorize(user_id=None):
    flow = Flow.from_client_secrets_file(
        google_auth.client_secret_file,
        scopes=google_auth.scopes,
        redirect_uri=GOOGLE_REDIRECT_URI
    )
    authorization_url, state = flow.authorization_url(
        prompt='consent',
        access_type='offline',
        include_granted_scopes='true',

    )
    if user_id:
        user = User.query.filter_by(id=user_id).first()
        user.state = state
        db.session.add(user)
        db.session.commit()
        return authorization_url

    else:
        user = User.query.filter_by(id=current_user.id).first()
        user.state = state
        db.session.add(user)
        db.session.commit()
        return redirect(authorization_url)


@oauth2.route('/google_oauth2callback')
def google_oauth2callback():
    try:
        state = request.args.get('state')
        user = User.query.filter_by(state=state).first()
        credentials = google_auth.build_credentials(request.url)
        google_auth.credentials_add_to_db(credentials, user.id)
        if not current_user:
            return {'message': 'ok'}
        else:
            return redirect(url_for('user_photos'))

    except Exception as e:
        print(e)
        return redirect(url_for('auth.login'))


@oauth2.route('/google_logout', methods=['GET'])
def google_logout():
    if current_user.is_authenticated:
        if 'credentials' in session:
            del session['credentials']
            return flask.redirect(url_for('oauth2.google_authorize'))
    return redirect(url_for('auth.login'))


def check_credentials(user_id=None, service='google'):
    user = User.query.filter_by(id=user_id).first()
    if service == 'google':
        with open('GOOGLE_CREDENTIALS.json', 'r') as json_file:
            google_credentials = json.load(json_file)
        if not user:
            if current_user.google_token is None and current_user.google_refresh_token is None:
                return redirect(url_for('oauth2.google_authorize'))
            return {'token': current_user.google_token,
                    'refresh_token': current_user.google_refresh_token,
                    'token_uri': google_credentials['token_uri'],
                    'client_id': google_credentials['client_id'],
                    'client_secret': google_credentials['client_secret'],
                    'scopes': google_credentials['scopes']}
        else:
            return {'token': user.google_token,
                    'refresh_token': user.google_refresh_token,
                    'token_uri': google_credentials['token_uri'],
                    'client_id': google_credentials['client_id'],
                    'client_secret': google_credentials['client_secret'],
                    'scopes': google_credentials['scopes']}


@oauth2.route('/dropbox_authorize')
def dropbox_authorize():
    if 'access_token' not in session:
        authorize_url = authenticator.start_auth()
        return flask.redirect(authorize_url)
    return redirect(url_for('photos.dropbox_photos'))


@oauth2.route('/dropbox_oauth2callback')
def dropbox_oauth2callback():
    try:
        session['access_token'], session['user_id'] = authenticator.finish_auth(request.args)
    except Exception as e:
        print(e)
        return redirect(url_for('index'))
    return redirect(url_for('photos.dropbox_photos'))


@oauth2.route('/dropbox_logout')
def dropbox_logout():
    if current_user.is_authenticated:
        if 'access_token' in session:
            del session['access_token'], session['user_id']
            print(session)
            session.modified = True
            authorize_url = authenticator.start_auth()
            return flask.redirect(authorize_url)
    return redirect(url_for('auth.login'))


@oauth2.route('/icloud_authorize', methods=['GET', 'POST'])
def icloud_authorize():
    form = IcloudLoginForm()
    if request.method == 'POST' and form.validate():
        try:
            icloud_user = keyring.get_password("pyicloud", form.apple_id.data)
            api = PyiCloudService(form.apple_id.data, form.password.data)
            api.authenticate(force_refresh=True)
            if current_user:
                user = User.query.filter_by(email=current_user.email).first()
                user.apple_id = form.apple_id.data
            db.session.commit()
            keyring.set_password("pyicloud", form.apple_id.data, form.password.data)

            if api.requires_2fa:
                return redirect(url_for('oauth2.icloud_verify_2fa', apple_id=form.apple_id.data))
            elif api.requires_2sa:
                return redirect(url_for('oauth2.icloud_verify_2sa', apple_id=form.apple_id.data))
            else:
                return redirect(url_for('photos.icloud_photos'))

        except PyiCloudFailedLoginException:
            flash('invalid Apple id or password')
            return redirect(url_for('oauth2.icloud_authorize', user=current_user))

    return render_template('oauth_templates/icloud_login.html', form=form)


def icloud_api_authorize():
    pass

# @oauth2.route('/', methods=['GET', 'POST'])
# def icloud_authorize():
#     if current_user.is_authenticated:
#         form = IcloudLoginForm()
#         if request.method == 'POST' and form.validate():
#             try:
#
#             except PyiCloudFailedLoginException:
#                 flash('invalid login')
#                 return redirect(url_for('oauth2.icloud_authorize'))
#
#     return redirect(url_for('auth.login'))


@oauth2.route('/icloud_verify_2fa', methods=['GET', 'POST'])
def icloud_verify_2fa():
    form = VerifyVerificationCodeForm()

    if form.validate_on_submit():
        verification_code = form.code.data
        icloud_password = keyring.get_password("pyicloud", current_user.apple_id)
        api = PyiCloudService(current_user.apple_id, icloud_password)
        api.authenticate(force_refresh=True)
        result = api.validate_2fa_code(verification_code)
        if not result:
            flash('Invalid verification code')
            return redirect(url_for('oauth2.icloud_verify_2fa'))

        if not api.is_trusted_session:
            result = api.trust_session()
            if not result:
                flash('Failed to request trust. You will likely be prompted for the code again in the coming weeks')
                return redirect(url_for('oauth2.icloud_verify_2fa'))
        return redirect(url_for('photos.icloud_photos'))

    return render_template('oauth_templates/icloud_verify_2fa.html', form=form)


@oauth2.route('/icloud_verify_2sa', methods=['GET', 'POST'])
def icloud_verify_2sa(apple_id):
    form = ICloudVerifyForm()

    if form.validate_on_submit():
        security_code = form.code.data
        icloud_password = keyring.get_password("pyicloud", apple_id)
        api = PyiCloudService(apple_id, icloud_password)
        api.authenticate(force_refresh=True)
        devices = api.trusted_devices
        device_list = []
        for i, device in enumerate(devices):
            device_name = device.get('deviceName', "SMS to %s" % device.get('phoneNumber'))
            device_list.append((i, device_name))
        device_index = int(security_code)
        device = devices[device_index]

        if not api.send_verification_code(device):
            flash('Failed to send verification code')
            return redirect(url_for('oauth2.icloud_verify_2sa'))

        if not api.validate_verification_code(device, security_code):
            flash('Failed to verify verification code')
            return redirect(url_for('oauth2.icloud_verify_2sa'))

        # Логика для обработки успешной верификации 2SA
        return redirect(url_for('photos.icloud_photos'))

    return render_template('oauth_templates/icloud_verify_2sa.html', form=form)


api_icloud_authorize = reqparse.RequestParser()
api_icloud_authorize.add_argument("apple_id", type=str, help="photos_data is required", required=True)
api_icloud_authorize.add_argument("password", type=str, help="photos_data is required", required=True)


class IcloudAuthorize(Resource):
    @jwt_required()
    def post(self):
        try:
            user = User.query.filter_by(id=get_jwt_identity()).first()

            args = api_icloud_authorize.parse_args()
            apple_id = args.get('apple_id')
            password = args.get('password')

            apple_api = PyiCloudService(apple_id, password)
            apple_api.authenticate(force_refresh=True)
            if user:
                user = User.query.filter_by(email=user.email).first()
                user.apple_id = apple_id
            db.session.commit()
            keyring.set_password("pyicloud", apple_id, password)

            if apple_api.requires_2fa:
                return
            elif apple_api.requires_2sa:
                return
            else:
                return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200

        except PyiCloudFailedLoginException:
            return {'message': 'invalid Apple id or password'}, 400


api_icloud_authorize_verify_2fa = reqparse.RequestParser()
api_icloud_authorize_verify_2fa.add_argument("code", type=str, help="code is required", required=True)


class IcloudVerify2fa(Resource):
    @jwt_required()
    def post(self):
        args = api_icloud_authorize_verify_2fa.parse_args()
        print(args.get('code'))
        user = User.query.filter_by(id=get_jwt_identity()).first()
        icloud_api = user.icloud_api(args.get('code'))
        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200


api.add_resource(IcloudAuthorize, '/api/v1/icloud/auth')
api.add_resource(IcloudVerify2fa, '/api/v1/icloud/auth/verify_2fa')




