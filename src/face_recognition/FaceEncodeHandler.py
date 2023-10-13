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

import requests
from celery import shared_task
from celery.contrib.abortable import AbortableTask
from src.app.config import *

register_heif_opener()


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

    def download_face_photos(self, session, photo_ids, parent_id):
        face_file_name = {}
        existing_files = [file for root, dirs, files in os.walk(self.faces_directory) for file in files]
        for face_data in photo_ids:
            for photo_id, data in face_data.items():
                self.image_path = os.path.join(self.download_faces, f'{photo_id}.jpeg')
                if f'{data[1]}.jpeg' not in existing_files:
                    # os.remove(self.image_path)
                    image = face_recognition.load_image_file(self.image_path)
                    image_pil = Image.open(self.image_path)
                    width, height = image_pil.size
                    face_locations = None
                    if width > 4000 or height > 5000:
                        face_locations = face_recognition.face_locations(image)
                    else:
                        face_locations = face_recognition.face_locations(image, model='cnn')

                    if len(face_locations) == 0:
                        face_locations = face_recognition.face_locations(image, number_of_times_to_upsample=2)

                    photo_face_encoding = face_recognition.face_encodings(image, face_locations, model='small')
                    for face_encode, face_location in zip(photo_face_encoding, face_locations):
                        face_encode_data = (FaceEncode.query.join(Photos, FaceEncode.photo_id == Photos.id)
                                            .join(Users, Photos.user_id == Users.id).filter(
                            Users.parent_id == parent_id).all())
                        for face in face_encode_data:
                            face_code_lower = face.face_code.lower()

                            is_key_face = FaceEncode.query.filter_by(face_code=face.key_face).first()

                            face_dir = [face_code_lower[i:i + 2] for i in range(0, len(face_code_lower), 2)]
                            is_match = face_recognition.compare_faces([face_encode], pickle.loads(face.face_encode),
                                                                      tolerance=0.3)
                            if is_match and any(is_match) and is_key_face is not None:
                                if os.path.exists(os.path.join(self.faces_directory, face_dir[0], face_dir[1],
                                                               face_dir[2], f'{face.face_code}.jpeg')):
                                    break

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
                                pil_image.save(self.faces_directory + file)
                                face_file_name[data[0]] = file
                                count += 1

                                path = f'{face_dir[0]}'
                                count1 = 0
                                while count1 < 3:
                                    folder_path = os.path.join(self.faces_directory, path)
                                    if not os.path.exists(folder_path):
                                        os.makedirs(folder_path)
                                    count1 += 1
                                    if count1 < 3:
                                        path += f'/{face_dir[count1]}'

                                new_filename = f"{face.face_code}.jpeg"  # Имя файла с новым кодом и расширением
                                new_image_path = os.path.join(self.faces_directory, face_dir[0], face_dir[1],
                                                              face_dir[2], new_filename)
                                file = file.lstrip('/')
                                old_image_path = os.path.join(self.faces_directory, file)
                                os.rename(old_image_path, new_image_path)
                                break
                if os.path.exists(self.image_path):
                    os.remove(self.image_path)

    def face_recognition_handler(self, face_encodes):
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
                face = FaceEncode.query.filter_by(face_code=code1).first()
                if code1 in check_codes:
                    continue

                check_codes.append(code1)

                face.key_face = code1
                db.session.commit()

                match_photo_ids = {photo_id1: encode1}

                for j, entry2 in enumerate(face_encodes[i + 1:], start=i):
                    encode2 = list(entry2.values())[0][0]
                    photo_id2 = list(entry2.keys())[0]
                    code2 = list(entry2.values())[0][1]

                    if code2 in check_codes:
                        continue

                    is_match = face_recognition.compare_faces([encode1], encode2, tolerance=0.55)

                    if all(is_match):
                        match_photo_ids[photo_id2] = encode2
                        # check_codes.append(code2)
                        face1 = FaceEncode.query.filter_by(face_code=code2).first()
                        if code1 != code2:
                            face1.not_a_key = True
                        # face1.key_face = code1
                        db.session.commit()

                temp_dict = {}
                for key, val in match_photo_ids.items():
                    if key != photo_id1:
                        for k, entry in enumerate(face_encodes):
                            photo_id = list(entry.keys())[0]
                            encode = list(entry.values())[0][0]
                            code = list(entry.values())[0][1]

                            if code in check_codes:
                                continue

                            is_match = face_recognition.compare_faces([val], encode, tolerance=0.6)

                            if all(is_match):
                                temp_dict[photo_id] = encode
                                face1 = FaceEncode.query.filter_by(face_code=code).first()
                                # if not face1.key_face:
                                face1.key_face = code1
                                db.session.commit()
                                # check_ids.append(photo_id)
                                check_codes.append(code)

                            # elif photo_id in list(match_photo_ids.keys()):
                            #     del temp_dict[photo_id]

                match_photo_ids.update(temp_dict)
                faces = []
                face = FaceEncode.query.filter_by(face_code=code1).first()
                root_face = FaceEncode.query.filter_by(face_code=face.key_face).first()
                if root_face:
                    if root_face.face_code not in faces:
                        faces.append(root_face.key_face)
                        matches.append({photo_id1: [encode1, face.face_code, list(match_photo_ids.keys())]})
                else:
                    matches.append({photo_id1: [encode1, code1, list(match_photo_ids.keys())]})

            for data in matches:
                for key, val in data.items():
                    data[key] = [val[1], val[2]]
                    for i in val[2]:
                        faces = FaceEncode.query.filter_by(photo_id=i).all()
                        for face in faces:
                            if face.key_face is None:
                                face.key_face = val[1]
                            db.session.commit()

            print(matches)
            return matches

        except Exception as e:
            print(e)
            return ''

    def face_folders(self, face_encode):
        list_face_code = []

        existing_files = [file for root, dirs, files in os.walk(self.faces_directory) for file in files]
        family_face_recognition = self.face_recognition_handler(face_encode)
        for i in family_face_recognition:
            for photo_id, photo_ids in i.items():
                formatted_face_code = "/".join([photo_ids[0][i:i + 2] for i in range(0, len(photo_ids[0]), 2)])

                if f'{photo_ids[0]}.jpeg' in existing_files:
                    list_face_code.append({photo_id: [formatted_face_code.lower(), f'{photo_ids[0]}']})

        return list_face_code
