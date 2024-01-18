import os
import time

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from PIL import Image
import face_recognition
import numpy as np
import pickle
from pillow_heif import register_heif_opener
from celery import Celery, chord
from flask_login import current_user
from src.app.config import *
from src.app.model import db, FaceEncode, User, Photo
import keyring
from pyicloud import PyiCloudService
from src.face_recognition.FaceEncodeHandler import download_face_photos, process_image, face_recognition_handler

import requests
from sqlalchemy.orm import joinedload

from celery import shared_task
from celery.result import allow_join_result
from celery.contrib.abortable import AbortableTask
from concurrent.futures import ThreadPoolExecutor, as_completed
import concurrent.futures

register_heif_opener()

task = Celery('tasks', broker=BROKER_URI, backend='db+' + SQLALCHEMY_DATABASE_URI)


@task.task(bind=True)
def download_photos(self, credentials, data, source_function, user_id):
    try:
        face_encodes = {}

        image_path = os.path.join(download_faces, f"{data}.jpeg")
        encode = None

        if source_function == '/photos/google_photos':
            service = build(serviceName=API_SERVICE_NAME,
                            version=API_VERSION,
                            credentials=Credentials.from_authorized_user_info(credentials),
                            static_discovery=False)

            request = service.mediaItems().get(mediaItemId=data).execute()
            download_url = request['baseUrl'] + '=d'  # Add '=d' to download the full-size photo
            response = requests.get(download_url)

            if response.status_code == 200:
                with open(image_path,
                          'wb') as photo_file:
                    photo_file.write(response.content)
                    photo_file.close()

                rotate_image(image_path)
                encode, location = process_image(image_path)
                face_encodes[data] = encode

            else:
                return {'message': 'Error downloading the photo'}
        if source_function == '/photos/icloud_photos':
            user = User.query.filter_by(id=user_id).first()
            icloud_password = keyring.get_password("pyicloud", user.apple_id)
            api = PyiCloudService(user.apple_id, icloud_password)
            api.authenticate(force_refresh=True)

            for photo in api.photos.albums['All Photos']:
                if photo.id == data:
                    photo_id_processed = data.replace('/', '____')
                    image_path = os.path.join(download_faces, f"{photo_id_processed}.jpeg")
                    download = photo.download()
                    with open(image_path, 'wb') as thumb_file:
                        thumb_file.write(download.raw.read())
                        thumb_file.close()
                    encode, location = process_image(image_path)
                    face_encodes[data] = encode

        photo = Photo.query.filter_by(photos_data=data).first()
        for faces in encode:
            code = generate_unique_code()
            face = FaceEncode(face_encode=faces,
                              photo_id=photo.id,
                              face_code=code,
                              key_face=code,
                              user_id=user_id)
            db.session.add(face)
        db.session.commit()
    except Exception as e:
        self.retry(exc=e, countdown=5)


@task.task()
def face_encode_handler(result, user_id):
    user = User.query.filter_by(id=user_id).options(joinedload(User.family)).first()
    family_user_ids = [member.id for member in user.family]

    # Получение всех FaceEncode для семьи пользователя
    people_faces = FaceEncode.query.filter(FaceEncode.user_id.in_(family_user_ids)).all()

    # Создание списка кодировок лиц
    # Получение существующих файлов
    existing_files = {file for root, dirs, files in os.walk(faces_dir) for file in files}

    face_encode = []
    for family_user in people_faces:
        people_face = FaceEncode.query.filter_by(user_id=family_user.id).all()
        for face in people_face:
            decoded_face = pickle.loads(face.face_encode)
            face_encode.append({face.photo_id: [decoded_face, face.face_code]})
    family_face_recognition = face_recognition_handler(face_encode)

    for data in family_face_recognition:
        for key, val in data.items():
            for i in val[1]:
                if i is not key:
                    faces = FaceEncode.query.filter_by(photo_id=i).all()

                    for face in faces:
                        key_face_check = FaceEncode.query.filter_by(key_face=face.face_code).all()
                        if face.key_face == face.face_code and not key_face_check:
                            face.key_face = val[0]
                db.session.commit()

    face_data_items = []
    x = []
    for i in family_face_recognition:
        for photo_id, photo_ids in i.items():

            photo = Photo.query.filter_by(id=photo_id).first()
            face = FaceEncode.query.filter_by(face_code=photo_ids[0]).first()
            if f'{photo_ids[0]}.jpeg' not in existing_files:
                if photo.photos_data not in x:
                    x.append(photo.photos_data)

                    face_data_items.append({photo.photos_data: [face.photo_id, photo_ids[0]]})

    # download_face_photos.delay(face_data_items, user.parent_id)
    cleanup_callback = cleanup_files.s(family_face_recognition)

    chord(download_face_photos.s(face_data_items, user.parent_id))(cleanup_callback)


@task.task()
def cleanup_files(result, family_face_recognition):
    for i in family_face_recognition:
        for photo_id, photo_ids in i.items():
            for del_photo_id in photo_ids[1]:
                del_photo = Photo.query.filter_by(id=del_photo_id).first()
                file_path = os.path.join(download_faces, f'{del_photo.photos_data}.jpeg')

                if os.path.exists(file_path):
                    os.remove(file_path)

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
