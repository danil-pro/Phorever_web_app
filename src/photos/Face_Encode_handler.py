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
# from pillow_heif import register_heif_opener


from src.app.model import db, FaceEncode, Users, Photos
import keyring
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException

import requests

from src.app.config import *

# register_heif_opener()


class FaceEncodeHandler:
    def __init__(self):
        self.directory = os.path.join(os.path.dirname(__file__), '..', '..', 'static',
                                      'img', 'user_photos')
        self.faces_directory = os.path.join(os.path.dirname(__file__), '..', '..', 'static',
                                            'img', 'user_photos', 'faces')
        self.download_faces = os.path.join(os.path.dirname(__file__), '..', '..', 'static',
                                           'img', 'user_photos', 'faces', 'download_face')
        self.image_path = ''
        self.file_name = {}

    def download_photos(self, credentials, photo_ids, source_function, key=None):
        if source_function == '/photos/google_photos':
            service = build(serviceName=API_SERVICE_NAME,
                            version=API_VERSION,
                            credentials=Credentials.from_authorized_user_info(credentials),
                            static_discovery=False)

            for photo_id in photo_ids:
                request = service.mediaItems().get(mediaItemId=photo_id).execute()
                download_url = request['baseUrl'] + '=d'  # Add '=d' to download the full-size photo
                response = requests.get(download_url)

                self.image_path = os.path.join(self.directory, request['filename'])

                if response.status_code == 200:
                    self.file_name[photo_id] = request['filename']
                    with open(self.image_path,
                              'wb') as photo_file:
                        photo_file.write(response.content)
                        photo_file.close()

                    self.rotate_image(key)

                else:
                    print('Error downloading the photo')
        if source_function == '/photos/icloud_photos':
            icloud_password = keyring.get_password("pyicloud", credentials['apple_id'])
            api = PyiCloudService(credentials['apple_id'], icloud_password)
            api.authenticate(force_refresh=True)

            for photo in api.photos.albums['All Photos']:
                for photo_id in photo_ids:
                    if photo.id == photo_id:

                        self.image_path = os.path.join(self.directory, photo.filename)

                        self.file_name[photo_id] = photo.filename
                        download = photo.download()
                        with open(self.image_path, 'wb') as thumb_file:
                            thumb_file.write(download.raw.read())

                        if '.HEIC' in photo.filename:
                            image = Image.open(self.image_path)
                            image.convert('RGB').save(
                                os.path.join(self.directory, 'output', os.path.splitext(photo.filename)[0] + '.jpg'))

        return self.face_encode_handler(self.file_name)

    def download_face_photos(self, session, photo_ids, parent_id):
        face_file_name = {}
        existing_files = [file for root, dirs, files in os.walk(self.faces_directory) for file in files]
        for face_data in photo_ids:
            for photo_id, data in face_data.items():
                photo = Photos.query.filter_by(photos_data=photo_id).first()
                with open('GOOGLE_CREDENTIALS.json', 'r') as json_file:
                    google_credentials = json.load(json_file)
                if f'{data[1]}.jpeg' not in existing_files:
                    self.image_path = os.path.join(self.download_faces, f'{data[1]}.jpeg')
                    if photo.service == '/photos/google_photos':
                        google_credentials['token'] = photo.token
                        google_credentials['refresh_token'] = photo.refresh_token
                        service = build(serviceName=API_SERVICE_NAME,
                                        version=API_VERSION,
                                        credentials=Credentials.from_authorized_user_info(google_credentials),
                                        static_discovery=False)

                        request = service.mediaItems().get(mediaItemId=photo_id).execute()
                        download_url = request['baseUrl'] + '=d'  # Add '=d' to download the full-size photo
                        response = requests.get(download_url)

                        if response.status_code == 200:
                            with open(self.image_path,
                                      'wb') as photo_file:
                                photo_file.write(response.content)
                                photo_file.close()

                            self.rotate_image(True)
                    if photo.service == '/photos/icloud_photos':
                        icloud_password = keyring.get_password("pyicloud", session['icloud_credentials']['apple_id'])
                        api = PyiCloudService(session['icloud_credentials']['apple_id'], icloud_password)
                        api.authenticate(force_refresh=True)

                        for photo in api.photos.albums['All Photos']:
                            for icloud_photo_id in photo_ids:
                                for icloud_id, _ in icloud_photo_id.items():
                                    if photo.id == icloud_id:

                                        download = photo.download()
                                        with open(self.image_path, 'wb') as thumb_file:
                                            thumb_file.write(download.raw.read())

                    image = face_recognition.load_image_file(self.image_path)
                    face_locations = face_recognition.face_locations(image)

                    count = 1
                    for face_location in face_locations:
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
                        pil_image.save(self.faces_directory + file)
                        face_file_name[data[0]] = file
                        count += 1

        self.face_directory(parent_id)

    def face_directory(self, parent_id):
        faces = {}
        for filename in os.listdir(self.faces_directory):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):

                image_path = os.path.join(self.faces_directory, filename)

                image = face_recognition.load_image_file(image_path)
                face_locations = face_recognition.face_locations(image)
                photo_face_encoding = face_recognition.face_encodings(image, face_locations, model='large')
                face_encode_data = (FaceEncode.query.join(Photos, FaceEncode.photo_id == Photos.id)
                                    .join(Users, Photos.user_id == Users.id).filter(Users.parent_id == parent_id).all())
                for face in face_encode_data:
                    face_code_lower = face.face_code.lower()
                    face_dir = [face_code_lower[i:i + 2] for i in range(0, len(face_code_lower), 2)]
                    is_match = face_recognition.compare_faces(photo_face_encoding, pickle.loads(face.face_encode),
                                                              tolerance=0.55)
                    if all(is_match):
                        path = f'{face_dir[0]}'
                        count = 0
                        while count < 3:
                            folder_path = os.path.join(self.faces_directory, path)
                            if not os.path.exists(folder_path):
                                os.makedirs(folder_path)
                            count += 1
                            if count < 3:
                                path += f'/{face_dir[count]}'

                        new_filename = f"{face.face_code}.jpeg"  # Имя файла с новым кодом и расширением
                        new_image_path = os.path.join(self.faces_directory, face_dir[0], face_dir[1],
                                                      face_dir[2], new_filename)

                        # Переименовываем файл
                        os.rename(image_path, new_image_path)
                        break
                    # if not found_match:
                    #     FaceEncode.query.filter_by(face_code=face.face_code).delete()
                    #     db.session.commit()
                    #     found_match = False
                    #     break

        for filename in os.listdir(self.download_faces):
            if filename:
                os.remove(os.path.join(self.download_faces, filename))

        for filename in os.listdir(self.faces_directory):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                os.remove(os.path.join(self.faces_directory, filename))

        return faces

    def rotate_image(self, key=None):
        image = Image.open(self.image_path)
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
            rotated_image.save(self.image_path)

    def face_encode_handler(self, photo_list):
        try:
            face_encode = {}

            for photo_id, file_name in photo_list.items():
                image_path = os.path.join(self.directory, file_name)
                if '.HEIC' in file_name:
                    temp_img = Image.open(image_path)
                    jpeg_photo = image_path.replace('.HEIC', '.jpeg')
                    temp_img.save(jpeg_photo)
                image = face_recognition.load_image_file(image_path)
                face_locations = face_recognition.face_locations(image)
                if len(face_locations) == 0:
                    face_locations = face_recognition.face_locations(image, number_of_times_to_upsample=2)
                photo_face_encoding = face_recognition.face_encodings(image, face_locations, model='large')

                face_encodes = []
                for one_face_encode in photo_face_encoding:
                    face_encode_xyz = np.array(one_face_encode)
                    face_encodes.append(pickle.dumps(face_encode_xyz))

                face_encode[photo_id] = face_encodes

                os.remove(image_path)

            return face_encode
        except Exception as e:
            print(e)

    def face_recognition_handler(self, face_encodes):
        try:
            matches = []

            check_ids = []
            check_codes = []
            all_ids = []
            for entry in face_encodes:
                for i in entry.keys():
                    all_ids.append(i)

            pair = [x for x in all_ids if all_ids.count(x) > 1]

            not_pair_face_encodes = [entry for entry in face_encodes if list(entry.keys())[0] not in pair]
            pair_face_encodes = [entry for entry in face_encodes if list(entry.keys())[0] in pair]
            for i, entry1 in enumerate(face_encodes):
                encode1 = list(entry1.values())[0][0]
                photo_id1 = list(entry1.keys())[0]
                code1 = list(entry1.values())[0][1]

                if code1 in check_codes:
                    continue

                match_photo_ids = {photo_id1: encode1}

                for j, entry2 in enumerate(face_encodes[i + 1:], start=i):
                    encode2 = list(entry2.values())[0][0]
                    photo_id2 = list(entry2.keys())[0]
                    code2 = list(entry2.values())[0][1]

                    if code2 in check_codes:
                        continue

                    is_match = face_recognition.compare_faces([encode1], encode2, tolerance=0.576)

                    if all(is_match):
                        match_photo_ids[photo_id2] = encode2
                        check_codes.append(code2)
                        check_ids.append(photo_id2)
                temp_dict = {}
                for key, val in match_photo_ids.items():
                    if key != photo_id1:
                        for k, entry in enumerate(face_encodes):
                            photo_id = list(entry.keys())[0]
                            encode = list(entry.values())[0][0]
                            code = list(entry.values())[0][1]

                            if code in check_codes:
                                continue

                            is_match = face_recognition.compare_faces([val], encode, tolerance=0.576)

                            if all(is_match):
                                temp_dict[photo_id] = encode
                                # check_ids.append(photo_id)
                                check_codes.append(code)
                            # elif photo_id in list(match_photo_ids.keys()):
                            #     del temp_dict[photo_id]

                match_photo_ids.update(temp_dict)

                matches.append({photo_id1: [encode1, code1, list(match_photo_ids.keys())]})

            # for i, entry1 in enumerate(pair_face_encodes):
            #     encode11 = list(entry1.values())[0][0]
            #     photo_id11 = list(entry1.keys())[0]
            #     for data in matches:
            #         for key1, val1 in data.items():
            #             if photo_id11 in val1[2]:
            #                 continue
            #             is_match = face_recognition.compare_faces([encode11], val1[0])
            #             if all(is_match):
            #                 val1[2].append(photo_id11)

            for data in matches:
                for key, val in data.items():
                    data[key] = [val[1], val[2]]

            print(matches)
            return matches

        except Exception as e:
            print(e)
            return ''
