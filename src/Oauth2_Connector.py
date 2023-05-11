# import flask
import asyncio
import json

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
import aiohttp


import dropbox
from dropbox.oauth import DropboxOAuth2Flow
from dropbox.exceptions import AuthError
from dropbox import files, sharing


import config

from concurrent.futures import ThreadPoolExecutor
import httpx
# import datetime
#
# import httplib2


# GOOGLE_REDIRECT_URI = config.GOOGLE_REDIRECT_URI
# app = flask.Flask(__name__)


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

    async def photos(self, credentials):
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
            photos_data = []
            next_page_token = None

            while True:
                params = {'pageSize': 100}
                if next_page_token:
                    params['pageToken'] = next_page_token

                async with session.get('https://photoslibrary.googleapis.com/v1/mediaItems',
                                       headers={'Authorization': f'Bearer {credentials.token}'},
                                       params=params) as response:
                    data = await response.json()
                    if not data:
                        return None
                    for item in data['mediaItems']:
                        media_meta_data = item.get('mediaMetadata')
                        video = media_meta_data.get('video')
                        if not video:
                            photo_data = {}
                            photo_data['baseUrl'] = item.get('baseUrl')
                            photo_data['photoId'] = item.get('id')
                            photos_data.append(photo_data)

                    next_page_token = data.get('nextPageToken')
                    if not next_page_token:
                        break
            return photos_data


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

    async def get_all_preview_urls(self, dbx):
        # Получаем список файлов
        files = await asyncio.to_thread(dbx.files_list_folder, '', recursive=True)
        if not files:
            return None
        # Разбиваем список файлов на подсписки
        chunks = [files.entries[i:i + 100] for i in range(0, len(files.entries), 100)]

        # Запускаем получение ссылок на превью для каждого подсписка
        # print(chunks)
        tasks = []
        for chunk in chunks:
            task = asyncio.create_task(self.get_preview_urls(dbx, chunk, files))
            tasks.append(task)
            break

        # Получаем все ссылки на превью
        preview_urls = []
        for result in await asyncio.gather(*tasks):
            preview_urls.extend(result)

        return preview_urls

    async def get_preview_urls(self, dbx, chunk, files):
        preview_urls = []
        cursor = None
        try:
            while True:
                if cursor:
                    files = await asyncio.to_thread(dbx.files_list_folder_continue, cursor)
                for entry in chunk:
                    if isinstance(entry, dropbox.files.FileMetadata) and entry.name.lower().endswith(
                            ('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                        try:
                            shared_links = dbx.sharing_get_shared_links(path=entry.path_display)
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
                if not files.has_more:
                    break
                cursor = files.cursor
                if len(preview_urls) > 100:
                    break
        except Exception as e:
            print(e)
        return preview_urls
