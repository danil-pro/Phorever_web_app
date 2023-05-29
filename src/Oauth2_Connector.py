# import flask
import asyncio
import json

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
# from google.api_core.page_iterator_async import AsyncGRPCIterator
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

    def photos(self, credentials):
        photos_data = []
        try:
            service = build(self.api_service_name, self.api_version, credentials=credentials, static_discovery=False)
            next_page_token = ''
            while next_page_token is not None:
                results = service.mediaItems().list(
                    pageSize=100,
                    pageToken=next_page_token,
                    fields='nextPageToken,mediaItems(id,baseUrl,mediaMetadata)'
                ).execute()
                items = results.get('mediaItems', [])
                for item in items:
                    media_meta_data = item.get('mediaMetadata')
                    video = media_meta_data.get('video')
                    if not video:
                        photo_data = {'baseUrl': item.get('baseUrl'), 'photoId': item.get('id')}
                        photos_data.append(photo_data)
                next_page_token = results.get('nextPageToken')
        except HttpError as error:
            print(f"An error occurred: {error}")
        return photos_data

    def get_albums_data(self, credentials, album_id):
        service = build(self.api_service_name, self.api_version, credentials=credentials, static_discovery=False)

        photos = service.mediaItems().search(body={'albumId': album_id}).execute()
        product_url = service.albums().get(albumId=album_id).execute()
        photo_data = []
        if 'mediaItems' in photos:
            for photo in photos['mediaItems']:
                base_url = photo['baseUrl']
                photo_data.append(base_url)
        photo_data.append(product_url['productUrl'])

        return photo_data

    def get_albums(self, credentials, album_id):
        try:
            service = build(self.api_service_name, self.api_version, credentials=credentials, static_discovery=False)
            title_list = []
            for i in album_id:
                try:
                    list_shared_albums = service.albums().get(albumId=i).execute()
                    album_data = {'title': list_shared_albums.get('title'),
                                  'id': list_shared_albums.get('id'),
                                  'productUrl': list_shared_albums.get('productUrl'),
                                  'shareableUrl': list_shared_albums.get('shareableUrl')}
                    title_list.append(album_data)
                except HttpError as error:
                    if error.resp.status == 404:
                        print(f"Альбом с ID '{i}' не найден.")
                        continue
                    else:
                        raise error
            return title_list
        except Exception as e:
            print(str(e))
            return None

    def create_shared_album(self, credentials, title='Phorever'):
        # Set album parameters
        service = build(self.api_service_name, self.api_version, credentials=credentials, static_discovery=False)
        album_body = {
            'album': {
                'title': title,
                'shareInfo': {
                    'sharedAlbumOptions': {
                        'isCollaborative': True,
                        'isCommentable': True
                    }
                }
            }
        }
        created_album = service.albums().create(body=album_body).execute()
        service.albums().share(albumId=created_album['id'], body={
            'sharedAlbumOptions': {
                'isCollaborative': True,
                'isCommentable': True
            }}).execute()
        return created_album['id']

    def add_photos_to_album(self, credentials, album_id, photo_ids):
        service = build(self.api_service_name, self.api_version, credentials=credentials, static_discovery=False)

        response = service.albums().batchAddMediaItems(albumId=album_id, body={"mediaItemIds": photo_ids}).execute()

        return response


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
