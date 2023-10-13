from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.app.config import *
import random
import string
from src.app.model import Photos, FaceEncode, Person
from src.face_recognition.FaceEncodeHandler import FaceEncodeHandler


def photo_from_google(credentials, page_token=None):
    photos_data = []
    try:
        service = build(API_SERVICE_NAME, API_VERSION, credentials=credentials, static_discovery=False)
        results = service.mediaItems().list(
            pageSize=100,
            pageToken=page_token,
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
        return [], None  # Return empty list and None for next_page_token in case of error
    return photos_data, next_page_token

