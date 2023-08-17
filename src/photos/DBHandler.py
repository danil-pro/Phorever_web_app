from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

from flask import redirect, url_for
from PIL import Image
import face_recognition
import numpy as np
from itertools import combinations
import pickle
from collections import Counter
import re
import itertools
import keyring
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException

import requests

from src.app.config import *

from src.app.model import Photos
import json


class DBHandler:
    def __init__(self):
        pass

    def get_photos_from_db(self, user_photos, credentials):
        photo_url = {}
        google_photo_ids = [photo.photos_data for photo in user_photos if
                            photo.service == '/photos/google_photos']
        dropbox_photos_urls = [photo.photos_data for photo in user_photos if
                               photo.service == '/photos/dropbox_photos']
        icloud_photos_ids = [photo.photos_data for photo in user_photos if
                             photo.service == '/photos/icloud_photos']

        if google_photo_ids:
            photo_tokens = [photo.token for photo in user_photos]
            unique_photo_tokens = []
            for token in photo_tokens:
                if token not in unique_photo_tokens:
                    unique_photo_tokens.append(token)

            photo_refresh_tokens = [photo.refresh_token for photo in user_photos]
            unique_photo_refresh_tokens = []
            for refresh_token in photo_refresh_tokens:
                if refresh_token not in unique_photo_refresh_tokens:
                    unique_photo_refresh_tokens.append(refresh_token)
            with open('GOOGLE_CREDENTIALS.json', 'r') as json_file:
                google_credentials = json.load(json_file)

            for token, refresh_token in zip(unique_photo_tokens, unique_photo_refresh_tokens):

                google_credentials['token'] = token
                google_credentials['refresh_token'] = refresh_token
                google_photos = [photo.photos_data for photo in user_photos if
                                 photo.service == '/photos/google_photos' and photo.token == token]

                try:
                    photo_iterator = iter(google_photos)
                    drive = build(serviceName=API_SERVICE_NAME,
                                  version=API_VERSION,
                                  credentials=Credentials.from_authorized_user_info(google_credentials),
                                  static_discovery=False)
                    while True:
                        chunk = list(itertools.islice(photo_iterator, 50))
                        if not chunk:
                            break
                        response = drive.mediaItems().batchGet(mediaItemIds=chunk).execute()
                        if 'mediaItemResults' in response:
                            for items in response['mediaItemResults']:
                                if 'mediaItem' in items:
                                    media_item = items['mediaItem']
                                    media_meta_data = media_item['mediaMetadata']
                                    photo_id = Photos.query.filter_by(photos_data=media_item['id']).first()
                                    if 'description' not in media_item:
                                        photo_url[photo_id.id] = {'baseUrl': media_item['baseUrl'],
                                                                  'description': 'Empty description',
                                                                  'creationTime':
                                                                      media_meta_data['creationTime'].split('T')[0]}
                                    else:
                                        photo_url[photo_id.id] = {'baseUrl': media_item['baseUrl'],
                                                                  'description': media_item['description'],
                                                                  'creationTime':
                                                                      media_meta_data['creationTime'].split('T')[0]}

                        break

                except RefreshError as e:
                    credentials_dict = Credentials(
                        **credentials)

                    revoke_token = requests.post(REVOKE_TOKEN,
                                                 params={'token': credentials_dict.token},
                                                 headers={'content-type': 'application/x-www-form-urlencoded'})

                    status_code = getattr(revoke_token, 'status_code')
                    if status_code == 200:
                        print('ok')
                    else:
                        print('An error occurred.' + str(status_code) + str(e))
                        return 'An error occurred.' + str(status_code) + str(e)

        if dropbox_photos_urls:
            for url in dropbox_photos_urls:
                photo_id = Photos.query.filter_by(photos_data=url).first()
                photo_url[photo_id.id] = {'baseUrl': url,
                                          'description': 'Empty description',
                                          'creationTime': '0000-00-00'}
        if icloud_photos_ids:
            try:
                photo_data_dict = {}  # Dictionary to store photo data

                for icloud_photo_id in icloud_photos_ids:
                    photo_id = Photos.query.filter_by(photos_data=icloud_photo_id).first()
                    icloud_password = keyring.get_password("pyicloud", photo_id.apple_id)

                    if photo_id.apple_id not in photo_data_dict:
                        api = PyiCloudService(photo_id.apple_id, icloud_password)
                        # api.authenticate(force_refresh=True)
                        photo_data_dict[photo_id.apple_id] = {}  # Initialize a new inner dictionary for each apple_id

                        for photo in api.photos.albums['All Photos']:
                            for version, data in photo.versions.items():
                                if data['type'] == 'public.jpeg':
                                    photo_data_dict[photo_id.apple_id][photo.id] = {'baseUrl': data['url'],
                                                                                    'creationTime': photo.created}

                for icloud_photo_id in icloud_photos_ids:
                    photo_id = Photos.query.filter_by(photos_data=icloud_photo_id).first()

                    if photo_id.apple_id in photo_data_dict:
                        apple_id_data = photo_data_dict[photo_id.apple_id]
                        for key, val in apple_id_data.items():
                            if icloud_photo_id == key:
                                photo_url[photo_id.id] = {'baseUrl': val['baseUrl'],
                                                          'description': 'Empty description',
                                                          'creationTime': str(val['creationTime']).split()[0]}
            except PyiCloudFailedLoginException:
                return ''

        return photo_url

    def get_photo_data_from_db(self, user_photo, credentials):
        if user_photo.service == '/photos/google_photos':
            user_token = credentials['token']
            user_refresh_token = credentials['refresh_token']
            credentials['token'] = user_photo.token
            credentials['refresh_token'] = user_photo.refresh_token
            drive = build(serviceName=API_SERVICE_NAME,
                          version=API_VERSION,
                          credentials=Credentials.from_authorized_user_info(credentials),
                          static_discovery=False)
            response = drive.mediaItems().get(mediaItemId=user_photo.photos_data).execute()
            credentials['token'] = user_token
            credentials['refresh_token'] = user_refresh_token
            return response['baseUrl']
        else:
            return user_photo.photos_data
