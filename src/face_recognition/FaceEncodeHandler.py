import pickle

import face_recognition
import numpy as np
from PIL import Image
from celery import Celery, shared_task
from pillow_heif import register_heif_opener

from src.app.config import *
from src.app.model import db, FaceEncode, User, Photo, Person
from src.photos.DBHandler import DBHandler

db_handler = DBHandler()

register_heif_opener()

task = Celery('tasks', broker=BROKER_URI, backend='db+' + SQLALCHEMY_DATABASE_URI)


@shared_task(bind=True)
def download_face_photos(self, photo_ids, user_id):
    db.engine.dispose()
    from run import app
    with app.app_context():

        user = User.query.filter_by(id=user_id).first()
        face_file_name = {}
        existing_files = [file for root, dirs, files in os.walk(faces_dir) for file in files]

        face_encode_data = (FaceEncode.query.join(Photo, FaceEncode.photo_id == Photo.id)
                            .join(User, Photo.user_id == User.id).filter(
            User.parent_id == user.parent_id).all())

        for face_data in photo_ids:
            for photo_id, data in face_data.items():
                image_path = os.path.join(download_faces, f'{data[0]}.jpeg')
                is_key_face = FaceEncode.query.filter_by(key_face=data[1]).all()
                if f'{data[1]}.jpeg' not in existing_files and is_key_face:
                    # os.remove(image_path)
                    photo_face_encoding, face_locations = process_image(image_path)
                    image = face_recognition.load_image_file(image_path)

                    for face_encode, face_location in zip(photo_face_encoding, face_locations):
                        for face in face_encode_data:
                            face_code_lower = face.face_code.lower()

                            face_dir = [face_code_lower[i:i + 2] for i in range(0, len(face_code_lower), 2)]
                            is_match = face_recognition.compare_faces([pickle.loads(face_encode)],
                                                                      pickle.loads(face.face_encode),
                                                                      tolerance=0.3)
                            if is_match and any(is_match):
                                if os.path.exists(os.path.join(faces_dir, face_dir[0], face_dir[1],
                                                               face_dir[2], f'{face.face_code}.jpeg')):
                                    break

                                new_person = Person()
                                new_person.face_code = face.face_code
                                new_person.parent_id = user.parent_id
                                db.session.add(new_person)
                                db.session.commit()

                                count = 1
                                top, right, bottom, left = face_location

                                # Вычисляем новые координаты обрезки
                                width = right - left
                                height = bottom - top
                                new_width = int(width * 2)
                                new_height = int(height * 2)
                                delta_width = (new_width - width) // 2
                                delta_height = (new_height - height) // 2

                                # Применяем новые координаты обрезки
                                new_top = max(0, top - delta_height)
                                new_right = min(image.shape[1], right + delta_width)
                                new_bottom = min(image.shape[0], bottom + delta_height)
                                new_left = max(0, left - delta_width)

                                face_image = image[new_top:new_bottom, new_left:new_right]
                                pil_image = Image.fromarray(face_image)
                                file = f'/{str(count)}_{data[1]}.jpeg'
                                pil_image.save(faces_dir + file)
                                face_file_name[data[0]] = file
                                count += 1

                                path = f'{face_dir[0]}'
                                count1 = 0
                                while count1 < 3:
                                    folder_path = os.path.join(faces_dir, path)
                                    if not os.path.exists(folder_path):
                                        os.makedirs(folder_path)
                                    count1 += 1
                                    if count1 < 3:
                                        path += f'/{face_dir[count1]}'

                                new_filename = f"{face.face_code}.jpeg"  # Имя файла с новым кодом и расширением
                                new_image_path = os.path.join(faces_dir, face_dir[0], face_dir[1],
                                                              face_dir[2], new_filename)

                                file = file.lstrip('/')
                                old_image_path = os.path.join(faces_dir, file)
                                os.rename(old_image_path, new_image_path)
                                break


def face_recognition_handler(face_encodes):
    try:
        matches = []

        check_codes = []
        all_ids = []
        for entry in face_encodes:
            for i in entry.keys():
                all_ids.append(i)

        for i, entry1 in enumerate(face_encodes):
            encode1 = list(entry1.values())[0][0]
            photo_id1 = list(entry1.keys())[0]
            code1 = list(entry1.values())[0][1]
            if code1 in check_codes:
                continue

            check_codes.append(code1)
            match_photo_ids = {photo_id1: [encode1, code1]}

            for j, entry2 in enumerate(face_encodes[i + 1:], start=i):
                encode2 = list(entry2.values())[0][0]
                photo_id2 = list(entry2.keys())[0]
                code2 = list(entry2.values())[0][1]

                if code2 in check_codes:
                    continue

                is_match = face_recognition.compare_faces([encode1], encode2, tolerance=0.6)

                if all(is_match):
                    match_photo_ids[photo_id2] = [encode2, code2]

            temp_dict = {}
            for key, val in match_photo_ids.items():
                if key != photo_id1:
                    for k, entry in enumerate(face_encodes):
                        photo_id = list(entry.keys())[0]
                        encode = list(entry.values())[0][0]
                        code = list(entry.values())[0][1]

                        if code in check_codes:
                            continue

                        is_match = face_recognition.compare_faces([val[0]], encode, tolerance=0.6)

                        if all(is_match):
                            temp_dict[photo_id] = [encode, code]
                            # face1 = FaceEncode.query.filter_by(face_code=code).first()
                            # # if not face1.key_face:
                            # face1.key_face = code1
                            # db.session.commit()
                            # check_ids.append(photo_id)
                            check_codes.append(code)

                        # elif photo_id in list(match_photo_ids.keys()):
                        #     del temp_dict[photo_id]

            match_photo_ids.update(temp_dict)

            matches.append({photo_id1: [code1, [{key: val[1]} for key, val in match_photo_ids.items()]]})

        # for data in matches:
        #     for key, val in data.items():
        #         data[key] = [val[1], val[2]]

        print(matches)
        return matches

    except Exception as e:
        print(e)
        return ''


def face_folders(face_encode):
    list_face_code = []

    existing_files = [file for root, dirs, files in os.walk(faces_dir) for file in files]
    family_face_recognition = face_recognition_handler(face_encode)
    for face_dict in family_face_recognition:

        root = list(face_dict.keys())[0]
        face_code = face_dict[root][0]
        formatted_face_code = "/".join([face_code[i:i + 2] for i in range(0, len(face_code), 2)])

        if f'{face_code}.jpeg' in existing_files:
            list_face_code.append({'face_path': f'../../static/img/user_photos/faces/'
                                                f'{formatted_face_code.lower()}/'
                                                f'{face_code}.jpeg',
                                   'face_code': f'{face_code}', 'photo_id': root})

    return list_face_code


def process_image(image_path):
    try:
        image = face_recognition.load_image_file(image_path)
        face_locations = face_recognition.face_locations(image)
        if face_locations:
            face_encodings = face_recognition.face_encodings(image, known_face_locations=face_locations, model='large')
            return [pickle.dumps(np.array(encoding)) for encoding in face_encodings], face_locations
        return None, None
    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        return None
