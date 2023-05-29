
from model import Photos, Users
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import *


class Worker:
    def __init__(self):
        pass

    def get_photos_from_db(self, user_photos, credentials):
        photo_url = []
        google_photo_ids = [photo.photos_data for photo in user_photos if
                            photo.service == '/photos/google_photos']
        dropbox_photos_urls = [photo.photos_data for photo in user_photos if
                               photo.service == '/photos/dropbox_photos']
        if google_photo_ids:
            drive = build(serviceName=API_SERVICE_NAME,
                          version=API_VERSION,
                          credentials=Credentials.from_authorized_user_info(credentials),
                          static_discovery=False)
            for i in range(0, len(google_photo_ids), 50):
                chunk = google_photo_ids[i:i + 50]
                response = drive.mediaItems().batchGet(mediaItemIds=chunk).execute()
                for items in response['mediaItemResults']:
                    media_item = items['mediaItem']
                    photo_url.append(media_item['baseUrl'])
        if dropbox_photos_urls:
            for url in dropbox_photos_urls:
                photo_url.append(url)
        return photo_url
