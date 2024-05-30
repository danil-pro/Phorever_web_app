from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from datetime import datetime, timedelta
import itertools

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
