import pickle
import time

import requests
from PIL import Image
from celery import Celery, chord
from celery import shared_task
from pillow_heif import register_heif_opener
from sqlalchemy.orm import joinedload

from src.app.config import *
from src.app.model import db, FaceEncode, User, Photo
from src.app.utils import generate_unique_code
from src.face_recognition.FaceEncodeHandler import download_face_photos, process_image, face_recognition_handler
from src.photos.DBHandler import DBHandler

db_handler = DBHandler()

register_heif_opener()

task = Celery('tasks', broker=BROKER_URI, backend='db+' + SQLALCHEMY_DATABASE_URI)


@shared_task(bind=True)
def download_photos(self, photo_url, photo_id, user_id):
    db.engine.dispose()
    from run import app
    face_encodes = {}
    image_path = os.path.join(download_faces, f"{photo_id}.jpeg")

    encode = None

    with app.app_context():

        download_url = photo_url + '=d'  # Add '=d' to download the full-size photo
        response = requests.get(download_url)

        if response.status_code == 200:
            with open(image_path,
                      'wb') as photo_file:
                photo_file.write(response.content)
                photo_file.close()

            rotate_image(image_path)
            encode, location = process_image(image_path)
            if encode and location:
                face_encodes[photo_id] = encode
            else:
                if os.path.exists(image_path):
                    os.remove(image_path)
                return {'message': 'not face'}

        else:
            return {'message': 'Error downloading the photo'}

    face_objects = []
    for faces in encode:
        # time.sleep(1)
        code = generate_unique_code()
        face = FaceEncode(
            face_encode=faces,
            photo_id=photo_id,
            face_code=code,
            key_face=code,
            user_id=user_id
        )
        face_objects.append(face)

    try:
        # time.sleep(1)
        db.session.bulk_save_objects(face_objects)
        db.session.commit()
    except Exception as e:
        print(e)
        db.session.rollback()  # Важно для предотвращения блокировок в базе данных
        raise  # Перевыброс для логгирования или дополнительной обработки ошибки
    print('ok')
    return {'message': 'not face'}


@shared_task(bind=True)
def face_encode_handler(x, y, user_id):
    user = User.query.filter_by(id=user_id).options(joinedload(User.family)).first()
    family_user_ids = [member.id for member in user.family]

    people_faces = FaceEncode.query.filter(FaceEncode.user_id.in_(family_user_ids)).all()

    existing_files = {file for root, dirs, files in os.walk(faces_dir) for file in files}

    face_encode = []
    for family_user in people_faces:
        time.sleep(1)
        people_face = FaceEncode.query.filter_by(user_id=family_user.id).all()
        for face in people_face:
            decoded_face = pickle.loads(face.face_encode)
            face_encode.append({face.photo_id: [decoded_face, face.key_face]})
    family_face_recognition = face_recognition_handler(face_encode)

    for data in family_face_recognition:
        for key, val in data.items():
            for face_data in val[1]:
                for face, code in face_data.items():
                    if code is not val[0]:
                        new_face = FaceEncode.query.filter_by(face_code=code).first()
                        new_face.key_face = val[0]
                    db.session.commit()

    face_data_items = []
    x = []
    for i in family_face_recognition:
        for photo_id, photo_ids in i.items():
            photo = Photo.query.filter_by(id=photo_id).first()
            face = FaceEncode.query.filter_by(face_code=photo_ids[0]).first()
            if f'{photo_ids[0]}.jpeg' not in existing_files:
                if photo.photo_url not in x:
                    x.append(photo.photo_url)

                    face_data_items.append({photo.photo_url: [face.photo_id, photo_ids[0]]})

    cleanup_callback = cleanup_files.s(family_face_recognition)

    chord(download_face_photos.s(face_data_items, user_id))(cleanup_callback)


@task.task()
def cleanup_files(result, family_face_recognition):
    for i in family_face_recognition:
        for root_photo_id, face_data in i.items():
            for face_dict in face_data[1]:
                for photo_id, face_code in face_dict.items():
                    file_path = os.path.join(download_faces, f'{photo_id}.jpeg')

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
