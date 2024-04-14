from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from datetime import datetime, timedelta
import itertools
import keyring
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException

from src.app.config import *

from src.app.model import Photo, db, User


class DBHandler:
    def __init__(self):
        pass

    @staticmethod
    def get_photos_from_db(user, credentials, update=False):
        user_photos = Photo.query.filter(User.parent_id == user.parent_id, Photo.user_id == User.id).all()

        google_photo_ids = [photo.photo_data for photo in user_photos if
                            photo.service == '/photos/google_photos']
        # dropbox_photo_urls = [photo.photo_data for photo in user_photos if
        #                        photo.service == '/photos/dropbox_photos']
        icloud_photos_ids = [photo.photo_data for photo in user_photos if
                             photo.service == '/photos/icloud_photos']

        if google_photo_ids:

            photo_created_at = [photo.created_at for photo in user_photos if
                                photo.service == '/photos/google_photos']
            new_photo = [photo.photo_data for photo in user_photos if
                         photo.service == '/photos/google_photos'
                         and photo.created_at == datetime.strptime('2023-07-13 15:30:45.123456',
                                                                   '%Y-%m-%d %H:%M:%S.%f')]
            time_difference = datetime.now() - photo_created_at[0]

            if time_difference >= timedelta(hours=1) or new_photo or update:

                photo_tokens = [photo.token for photo in user_photos if
                                photo.service == '/photos/google_photos']
                unique_photo_tokens = []
                for token in photo_tokens:
                    if token and token not in unique_photo_tokens:
                        unique_photo_tokens.append(token)

                photo_refresh_tokens = [photo.refresh_token for photo in user_photos if
                                        photo.service == '/photos/google_photos']
                unique_photo_refresh_tokens = []
                for refresh_token in photo_refresh_tokens:
                    if refresh_token and refresh_token not in unique_photo_refresh_tokens:
                        unique_photo_refresh_tokens.append(refresh_token)

                for token, refresh_token in zip(unique_photo_tokens, unique_photo_refresh_tokens):

                    credentials['token'] = token
                    credentials['refresh_token'] = refresh_token
                    google_photos = [photo.photo_data for photo in user_photos if
                                     photo.service == '/photos/google_photos' and photo.token == token]
                    try:
                        photo_iterator = iter(google_photos)
                        if new_photo:
                            photo_iterator = iter(new_photo)

                        auth_credentials = Credentials(token=token, refresh_token=refresh_token,
                                                       token_uri=credentials['token_uri'],
                                                       client_id=credentials['client_id'],
                                                       client_secret=credentials['client_secret'])
                        # if not auth_credentials.valid:
                        #     if auth_credentials.refresh_token:
                        auth_credentials.refresh(Request())

                        drive = build(serviceName=API_SERVICE_NAME,
                                      version=API_VERSION,
                                      credentials=auth_credentials,
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
                                        photo = Photo.query.filter_by(photo_data=media_item['id']).first()
                                        photo.photo_url = media_item['baseUrl']
                                        photo.google_token = auth_credentials.token
                                        photo.created_at = datetime.now()
                                        photo_meta_data = photo.meta_data
                                        if not photo_meta_data.creation_data:
                                            photo_meta_data.creation_data = \
                                                int(datetime.strptime(media_meta_data['creationTime'].
                                                                      split('T')[0],
                                                                      '%Y-%m-%d').timestamp())
                                        if 'description' in media_item and not photo_meta_data.description:
                                            photo_meta_data.description = media_item['description']
                                        db.session.commit()
                            break

                    except RefreshError as e:
                        print(e)
                        return 'An error occurred.' + str(e)

        # if dropbox_photo_urls:
        #     for url in dropbox_photo_urls:
        #         photo_id = Photo.query.filter_by(photo_data=url).first()
        #         photo_url[photo_id.id] = {'baseUrl': url,
        #                                   'description': 'Empty description',
        #                                   'creationTime': '0000-00-00'}
        if icloud_photos_ids:
            photo_created_at = [photo.created_at for photo in user_photos if
                                photo.service == '/photos/icloud_photos']
            new_photo = [photo.photo_data for photo in user_photos if
                         photo.service == '/photos/icloud_photos'
                         and photo.created_at == datetime.strptime('2023-07-13 15:30:45.123456',
                                                                   '%Y-%m-%d %H:%M:%S.%f')]
            time_difference = datetime.now() - photo_created_at[0]

            if time_difference >= timedelta(hours=1) or new_photo or update:
                try:
                    photo_data_dict = {}  # Dictionary to store photo data

                    for icloud_photo_id in icloud_photos_ids:
                        photo_id = Photo.query.filter_by(photo_data=icloud_photo_id).first()
                        icloud_password = keyring.get_password("pyicloud", photo_id.apple_id)

                        if photo_id.apple_id not in photo_data_dict:
                            api = PyiCloudService(photo_id.apple_id, icloud_password)
                            api.authenticate(force_refresh=True)
                            photo_data_dict[
                                photo_id.apple_id] = {}  # Initialize a new inner dictionary for each apple_id

                            for photo in api.photos.albums['All Photos']:
                                for version, data in photo.versions.items():
                                    if data['type'] == 'public.jpeg':
                                        photo_data_dict[photo_id.apple_id][photo.id] = {'baseUrl': data['url'],
                                                                                        'creationTime': photo.created}

                    for icloud_photo_id in icloud_photos_ids:
                        photo = Photo.query.filter_by(photo_data=icloud_photo_id).first()

                        photo_meta_data = photo.meta_data
                        if photo.apple_id in photo_data_dict:
                            apple_id_data = photo_data_dict[photo.apple_id]
                            for key, val in apple_id_data.items():
                                if icloud_photo_id == key:
                                    photo.created_at = datetime.now()
                                    photo.photo_url = val['baseUrl']
                                    if not photo_meta_data.creation_data:
                                        photo_meta_data.creation_data = int(
                                            datetime.strptime(str(val['creationTime']).split()[0],
                                                              '%Y-%m-%d').timestamp())
                except PyiCloudFailedLoginException:
                    return ''

    @staticmethod
    def get_photo_data_from_db(user_photo, credentials):
        if user_photo.service == '/photos/google_photos':
            user_token = credentials['token']
            user_refresh_token = credentials['refresh_token']
            credentials['token'] = user_photo.token
            credentials['refresh_token'] = user_photo.refresh_token
            drive = build(serviceName=API_SERVICE_NAME,
                          version=API_VERSION,
                          credentials=Credentials.from_authorized_user_info(credentials),
                          static_discovery=False)
            response = drive.mediaItems().get(mediaItemId=user_photo.photo_data).execute()
            credentials['token'] = user_token
            credentials['refresh_token'] = user_refresh_token
            return response['baseUrl']
        else:
            return user_photo.photo_data
