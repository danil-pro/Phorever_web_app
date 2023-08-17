from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.app.config import *
import random
import string
from src.app.model import Photos, FaceEncode
from src.photos.Face_Encode_handler import FaceEncodeHandler


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


def generate_unique_code():
    while True:
        code = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        if not FaceEncode.query.filter_by(face_code=code).first():
            return code


def face_folders(face_encode, session, parent_id):
    faces_directory = os.path.join(os.path.dirname(__file__), '..', '..', 'static',
                                   'img', 'user_photos', 'faces')
    list_face_code = []
    family_user_faces = []
    x = []
    existing_files = [file for root, dirs, files in os.walk(faces_directory) for file in files]
    face_encode_handler = FaceEncodeHandler()
    family_face_recognition = face_encode_handler.face_recognition_handler(face_encode)
    for i in family_face_recognition:
        for photo_id, photo_ids in i.items():
            photo = Photos.query.filter_by(id=photo_id).first()
            face = FaceEncode.query.filter_by(face_code=photo_ids[0]).first()
            formatted_face_code = "/".join([photo_ids[0][i:i + 2] for i in range(0, len(photo_ids[0]), 2)])

            if f'{photo_ids[0]}.jpeg' not in existing_files:
                if photo_id not in x:
                    x.append(photo_id)
                    family_user_faces.append({photo.photos_data: [face.photo_id, photo_ids[0]]})
            if photo_id not in [item.get('photo_id') for item in list_face_code]:
                list_face_code.append({photo_id: [formatted_face_code.lower(), f'{photo_ids[0]}']})

    face_encode_handler.download_face_photos(session, family_user_faces, parent_id)
    print(family_user_faces)

    return list_face_code
