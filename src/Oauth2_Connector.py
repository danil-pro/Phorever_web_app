import flask

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

import dropbox
from dropbox.oauth import DropboxOAuth2Flow
from dropbox.exceptions import AuthError
from dropbox import files, sharing

import src.config

config = src.config

app = flask.Flask(__name__)


class GoogleOauth2Connect:
    def __init__(self, client_secret_file, scopes, api_service_name, api_version):
        self.client_secret_file = client_secret_file
        self.scopes = scopes
        self.api_service_name = api_service_name
        self.api_version = api_version

    def build_credentials(self, authorization_response):
        flow = Flow.from_client_secrets_file(
            self.client_secret_file, scopes=self.scopes)
        flow.redirect_uri = config.GOOGLE_REDIRECT_URI
        flow.fetch_token(authorization_response=authorization_response)
        credentials = flow.credentials
        return credentials

    def credentials_to_dict(self, credentials):
        return {'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes}

    def photos(self, credentials):
        drive = build(self.api_service_name, self.api_version, credentials=credentials, static_discovery=False)
        base_url = []
        media_items = drive.mediaItems().list(pageSize=100).execute()
        next_page_token = media_items.get('nextPageToken')
        while next_page_token:
            media_items = drive.mediaItems().list(pageSize=100, pageToken=next_page_token).execute()
            next_page_token = media_items.get('nextPageToken')
            data = media_items.get('mediaItems')
            for i in data:
                media_meta_data = i.get('mediaMetadata')
                video = media_meta_data.get('video')
                if not video:
                    base_url.append(i.get('baseUrl'))
                if len(base_url) > 30:
                    break
        return base_url


class DropboxOauth2Connect:
    def __init__(self, app_key, app_secret, redirect_uri, session):
        self.app_key = app_key
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri
        self.session = session
        self.auth_flow = DropboxOAuth2Flow(
            consumer_key=app_key,
            consumer_secret=app_secret,
            redirect_uri=redirect_uri,
            session=session,
            csrf_token_session_key='dropbox-auth-csrf-token'
        )

    def start_auth(self):
        authorize_url = self.auth_flow.start()
        return authorize_url

    def finish_auth(self, request_args):
        try:
            result = self.auth_flow.finish(request_args)
            self.session['access_token'] = result.access_token
            self.session['user_id'] = result.user_id
            return self.session['access_token'], self.session['user_id']
        except AuthError as e:
            print(e)
            return False

    def get_dropbox_client(self):
        if 'access_token' in self.session:
            access_token = self.session['access_token']
            return dropbox.Dropbox(access_token)
        else:
            return None

    def get_preview_urls(self, dbx):
        result = dbx.files_list_folder("", recursive=True)
        preview_urls = []
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FileMetadata) and entry.name.lower().endswith(('.png', '.jpg', '.jpeg',
                                                                                              '.gif', '.bmp')):
                try:
                    shared_links = dbx.sharing_list_shared_links(entry.id)
                    if len(shared_links.links) > 0:
                        preview_url = shared_links.links[0].url.replace("?dl=0", "?raw=1")
                    else:
                        settings = dropbox.sharing.SharedLinkSettings(
                            requested_visibility=dropbox.sharing.RequestedVisibility.public)
                        shared_link = dbx.sharing_create_shared_link_with_settings(entry.id, settings)
                        preview_url = shared_link.url.replace("?dl=0", "?raw=1")
                except Exception as e:
                    print(e)
                    preview_url = None
                if preview_url:
                    preview_urls.append(preview_url)
                if len(preview_urls) > 10:
                    break
        return preview_urls
