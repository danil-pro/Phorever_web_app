from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

import requests

from src.app.config import *

from src.app.model import Photos


class DBHandler:
    def __init__(self):
        pass

    def get_photos_from_db(self, user_photos, credentials):
        photo_url = {}
        google_photo_ids = [photo.photos_data for photo in user_photos if
                            photo.service == '/photos/google_photos']
        dropbox_photos_urls = [photo.photos_data for photo in user_photos if
                               photo.service == '/photos/dropbox_photos']

        if google_photo_ids:
            user_token = credentials['token']
            user_refresh_token = credentials['refresh_token']
            for photo in user_photos:
                credentials['token'] = photo.token
                credentials['refresh_token'] = photo.refresh_token
                break
            try:
                while True:
                    drive = build(serviceName=API_SERVICE_NAME,
                                  version=API_VERSION,
                                  credentials=Credentials.from_authorized_user_info(credentials),
                                  static_discovery=False)
                    for i in range(0, len(google_photo_ids), 50):
                        chunk = google_photo_ids[i:i + 50]
                        response = drive.mediaItems().batchGet(mediaItemIds=chunk).execute()
                        for items in response['mediaItemResults']:
                            media_item = items['mediaItem']
                            media_meta_data = media_item['mediaMetadata']
                            photo_id = Photos.query.filter_by(photos_data=media_item['id']).first()
                            if 'description' not in media_item:
                                photo_url[photo_id.id] = {'baseUrl': media_item['baseUrl'],
                                                          'description': '',
                                                          'creationTime': media_meta_data['creationTime'].split('T')[0]}
                            else:
                                photo_url[photo_id.id] = {'baseUrl': media_item['baseUrl'],
                                                          'description': media_item['description'],
                                                          'creationTime': media_meta_data['creationTime'].split('T')[0]}

                    credentials['token'] = user_token
                    credentials['refresh_token'] = user_refresh_token
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
                photo_url[photo_id.id] = url
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
