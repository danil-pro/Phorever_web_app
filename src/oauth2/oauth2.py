import flask
from flask import *
from src.auth.auth import current_user

from google_auth_oauthlib.flow import Flow

from src.app.config import *
from src.oauth2.Oauth2_Connector import GoogleOauth2Connect, DropboxOauth2Connect
from src.app.Forms import IcloudLoginForm, VerifyVerificationCodeForm, ICloudVerifyForm
from src.app.model import Users, db

import keyring
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException


oauth2 = Blueprint('oauth2', __name__, template_folder='../templates', static_folder='../static')
current_dir = os.path.dirname(os.path.abspath(__file__))

CLIENT_SECRETS_FILE = CLIENT_SECRETS_FILE

absolute_path = os.path.join(current_dir, CLIENT_SECRETS_FILE)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

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
def google_authorize():
    flow = Flow.from_client_secrets_file(
        google_auth.client_secret_file,
        scopes=google_auth.scopes,
        redirect_uri=GOOGLE_REDIRECT_URI
    )
    authorization_url, state = flow.authorization_url(
        prompt='consent',
        access_type='offline',
        include_granted_scopes='true'
    )
    session['state'] = state
    return redirect(authorization_url)


@oauth2.route('/google_oauth2callback')
def google_oauth2callback():
    try:
        state = session['state']
        credentials = google_auth.build_credentials(request.url)
        session['credentials'] = google_auth.credentials_to_dict(credentials)

        return redirect(url_for('user_photos'))
    except Exception as e:
        print(e)
        return redirect(url_for('index'))


@oauth2.route('/google_logout', methods=['GET'])
def google_logout():
    if current_user.is_authenticated:
        if 'credentials' in session:
            del session['credentials']
            return flask.redirect(url_for('oauth2.google_authorize'))
    return redirect(url_for('auth.login'))


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
    if current_user.is_authenticated:
        form = IcloudLoginForm()
        if request.method == 'POST' and form.validate():
            try:
                icloud_user = keyring.get_password("pyicloud", form.apple_id.data)
                session['icloud_credentials'] = {'apple_id': form.apple_id.data}
                api = PyiCloudService(form.apple_id.data, form.password.data)
                session['icloud_credentials'] = {'apple_id': form.apple_id.data}
                keyring.set_password("pyicloud", form.apple_id.data, form.password.data)

                if api.requires_2fa:
                    return redirect(url_for('oauth2.icloud_verify_2fa'))
                elif api.requires_2sa:
                    return redirect(url_for('oauth2.icloud_verify_2sa', apple_id=form.apple_id.data))
                else:
                    return redirect(url_for('photos.icloud_photos'))

            except PyiCloudFailedLoginException:
                flash('invalid login')
                return redirect(url_for('oauth2.icloud_authorize'))

        return render_template('oauth_templates/icloud_login.html', form=form)

    return redirect(url_for('auth.login'))


@oauth2.route('/icloud_verify_2fa', methods=['GET', 'POST'])
def icloud_verify_2fa():
    form = VerifyVerificationCodeForm()

    if form.validate_on_submit():
        verification_code = form.code.data
        icloud_password = keyring.get_password("pyicloud", session['icloud_credentials']['apple_id'])
        api = PyiCloudService(session['icloud_credentials']['apple_id'], icloud_password)
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
def icloud_verify_2sa():
    form = ICloudVerifyForm()

    if form.validate_on_submit():
        security_code = form.code.data
        icloud_password = keyring.get_password("pyicloud", session['icloud_credentials']['apple_id'])
        api = PyiCloudService(session['icloud_credentials']['apple_id'], icloud_password)
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

