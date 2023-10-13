import os
import json

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError
from flask import redirect, url_for
from PIL import Image
import face_recognition
import numpy as np
from itertools import combinations
import pickle
from collections import Counter
import re
from pillow_heif import register_heif_opener

from src.app.model import db, FaceEncode, Users, Photos
import keyring
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException
from src.face_recognition.FaceEncodeHandler import FaceEncodeHandler

import requests
from celery import shared_task
from celery.contrib.abortable import AbortableTask
from src.app.config import *

register_heif_opener()
face_recognition_encode = FaceEncodeHandler()


@shared_task(bind=True, base=AbortableTask)
def download_photos(self, credentials, photo_ids, source_function, user_id):
    file_name = {}
    download_faces = os.path.join(os.path.dirname(__file__), '..', '..', 'static',
                                  'img', 'user_photos', 'faces', 'download_face')

    if source_function == '/photos/google_photos':
        service = build(serviceName=API_SERVICE_NAME,
                        version=API_VERSION,
                        credentials=Credentials.from_authorized_user_info(credentials),
                        static_discovery=False)

        for photo_data in photo_ids:
            photo_id, photo_url = photo_data.split('|')
            request = service.mediaItems().get(mediaItemId=photo_id).execute()
            download_url = request['baseUrl'] + '=d'  # Add '=d' to download the full-size photo
            response = requests.get(download_url)

            image_path = os.path.join(download_faces, f'{photo_id}.jpeg')

            if response.status_code == 200:
                file_name[photo_id] = f'{photo_id}.jpeg'
                with open(image_path,
                          'wb') as photo_file:
                    photo_file.write(response.content)
                    photo_file.close()

                rotate_image(image_path)

            else:
                print('Error downloading the photo')
    if source_function == '/photos/icloud_photos':
        icloud_password = keyring.get_password("pyicloud", credentials['apple_id'])
        api = PyiCloudService(credentials['apple_id'], icloud_password)
        api.authenticate(force_refresh=True)

        for photo in api.photos.albums['All Photos']:
            for photo_data in photo_ids:
                photo_id, photo_url = photo_data.split('|')
                if photo.id == photo_id:
                    image_path = os.path.join(download_faces, f'{photo_id}.jpeg')

                    file_name[photo_id] = f'{photo_id}.jpeg'
                    download = photo.download()
                    with open(image_path, 'wb') as thumb_file:
                        thumb_file.write(download.raw.read())
                        thumb_file.close()

    return face_encode_handler(file_name, user_id, credentials)


def face_encode_handler(photo_list, user_id, session):
    download_faces = os.path.join(os.path.dirname(__file__), '..', '..', 'static',
                                  'img', 'user_photos', 'faces', 'download_face')

    try:
        face_encode = {}

        for photo_id, file_name in photo_list.items():
            image_path = os.path.join(download_faces, file_name)

            image_pil = Image.open(image_path)
            width, height = image_pil.size
            image = face_recognition.load_image_file(image_path)
            face_locations = None
            if width > 4000 or height > 5000:
                face_locations = face_recognition.face_locations(image)
            else:
                face_locations = face_recognition.face_locations(image, model='cnn')

            if len(face_locations) == 0:
                face_locations = face_recognition.face_locations(image, number_of_times_to_upsample=2)

            photo_face_encoding = face_recognition.face_encodings(image, face_locations, model='small')

            face_encodes = []
            for one_face_encode in photo_face_encoding:
                face_encode_xyz = np.array(one_face_encode)
                face_encodes.append(pickle.dumps(face_encode_xyz))

            face_encode[photo_id] = face_encodes

            # os.remove(image_path)

        for photo_id, face_encode in face_encode.items():
            photo = Photos.query.filter_by(photos_data=photo_id).first()
            for faces in face_encode:
                code = generate_unique_code()
                face = FaceEncode(face_encode=faces,
                                  photo_id=photo.id,
                                  face_code=code,
                                  key_face=None,
                                  user_id=user_id)
                db.session.add(face)
        db.session.commit()

        user = Users.query.filter_by(id=user_id).first()
        current_user_family = Users.query.filter_by(parent_id=user.parent_id).all()

        face_encode = []
        for family_user in current_user_family:
            people_face = FaceEncode.query.filter_by(user_id=family_user.id).all()
            for face in people_face:
                decoded_face = pickle.loads(face.face_encode)
                face_encode.append({face.photo_id: [decoded_face, face.face_code]})

        family_user_faces = []
        x = []
        existing_files = [file for root, dirs, files in os.walk(os.path.join(os.path.dirname(__file__), '..', '..',
                                                                             'static',
                                                                             'img',
                                                                             'user_photos', 'faces')) for file in files]
        family_face_recognition = face_recognition_encode.face_recognition_handler(face_encode)
        for i in family_face_recognition:
            for photo_id, photo_ids in i.items():
                print(photo_ids)
                photo = Photos.query.filter_by(id=photo_id).first()
                face = FaceEncode.query.filter_by(face_code=photo_ids[0]).first()
                if f'{photo_ids[0]}.jpeg' not in existing_files:
                    if photo_id not in x:
                        x.append(photo_id)

                        family_user_faces.append({photo.photos_data: [face.photo_id, photo_ids[0]]})
        face_recognition_encode.download_face_photos(session, family_user_faces, user.parent_id)
        for i in family_face_recognition:
            for photo_id, photo_ids in i.items():
                for del_photo_id in photo_ids[1]:
                    del_photo = Photos.query.filter_by(id=del_photo_id).first()
                    file_path = os.path.join(download_faces, f'{del_photo.photos_data}.jpeg')

                    if os.path.exists(file_path):
                        os.remove(file_path)

    except Exception as e:
        print(e)


def rotate_image(image_path):
    image = Image.open(image_path)
    exif_orientation = 0x0112

    if hasattr(image, '_getexif') and isinstance(image._getexif(), dict):
        exif = image._getexif()
        if exif is not None and exif_orientation in exif:
            orientation = exif[exif_orientation]
            # Определение нужного угла поворота
            if orientation == 3:
                angle = 180
            elif orientation == 6:
                angle = 270
            elif orientation == 8:
                angle = 90
            else:
                angle = 0
        else:
            angle = 0
    else:
        angle = 0

    # Поворот изображения
    if angle != 0:
        rotated_image = image.rotate(angle, expand=True)
        rotated_image.save(image_path)
