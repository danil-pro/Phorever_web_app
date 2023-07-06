from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

from PIL import Image
import face_recognition
import numpy as np
from itertools import combinations
import pickle

import keyring
from pyicloud import PyiCloudService

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
        icloud_photos_ids = [photo.photos_data for photo in user_photos if
                             photo.service == '/photos/icloud_photos']

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
                                                          'description': 'Empty description',
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
                photo_url[photo_id.id] = {'baseUrl': url,
                                          'description': 'Empty description',
                                          'creationTime': '0000-00-00'}
        if icloud_photos_ids:
            photo_data_dict = {}  # Dictionary to store photo data

            for icloud_photo_id in icloud_photos_ids:
                photo_id = Photos.query.filter_by(photos_data=icloud_photo_id).first()
                icloud_password = keyring.get_password("pyicloud", photo_id.apple_id)

                if photo_id.apple_id not in photo_data_dict:
                    api = PyiCloudService(photo_id.apple_id,
                                          icloud_password)  # Register PyiCloudService only once per apple_id
                    photo_data_dict[photo_id.apple_id] = {}  # Initialize a new inner dictionary for each apple_id

                    for photo in api.photos.albums['All Photos']:
                        for version, data in photo.versions.items():
                            if data['type'] == 'public.jpeg':
                                photo_data_dict[photo_id.apple_id][photo.id] = {'baseUrl': data['url'],
                                                                                'creationTime': photo.created}

            for icloud_photo_id in icloud_photos_ids:
                photo_id = Photos.query.filter_by(photos_data=icloud_photo_id).first()

                if photo_id.apple_id in photo_data_dict:
                    apple_id_data = photo_data_dict[photo_id.apple_id]
                    for key, val in apple_id_data.items():
                        if icloud_photo_id == key:
                            photo_url[photo_id.id] = {'baseUrl': val['baseUrl'],
                                                      'description': 'Empty description',
                                                      'creationTime': str(val['creationTime']).split()[0]}

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

    def download_photos(self, credentials, photo_ids):
        service = build(serviceName=API_SERVICE_NAME,
                        version=API_VERSION,
                        credentials=Credentials.from_authorized_user_info(credentials),
                        static_discovery=False)
        file_name = {}

        for photo_id in photo_ids:
            request = service.mediaItems().get(mediaItemId=photo_id).execute()
            download_url = request['baseUrl'] + '=d'  # Add '=d' to download the full-size photo
            response = requests.get(download_url)

            image_path = os.path.join(os.path.dirname(__file__), '..', '..', 'static',
                                      'img', 'user_photos', request['filename'])

            if response.status_code == 200:
                file_name[photo_id] = request['filename']
                with open(image_path,
                          'wb') as photo_file:
                    photo_file.write(response.content)
                    photo_file.close()

                image = Image.open(image_path)
                exif_orientation = 0x0112
                width, height = image.size

                if width > 1000 and height > 1000:
                    new_size = (1000, 1000)
                    resized_image = image.resize(new_size)
                    resized_image.save(image_path)

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
            else:
                print('Error downloading the photo')

        return file_name

    def face_encode_handler(self, photo_list):
        try:
            face_encode = {}
            for photo_id, file_name in photo_list.items():
                image_path = os.path.join(os.path.dirname(__file__), '..', '..',
                                          'static', 'img', 'user_photos', file_name)
                image = face_recognition.load_image_file(image_path)
                face_locations = face_recognition.face_locations(image, model='cnn')
                print(f'There are {len(face_locations)} people in this image')
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
            checked_ids = set()  # Множество для хранения уже проверенных идентификаторов

            for i, entry1 in enumerate(face_encodes):
                encode1 = list(entry1.values())[0]
                photo_id1 = list(entry1.keys())[0]

                # Проверяем, что первый идентификатор еще не был проверен
                if photo_id1 in checked_ids:
                    continue

                photo_ids = {photo_id1}  # Создаем множество с идентификатором первого лица

                for j, entry2 in enumerate(face_encodes[i + 1:], start=i + 1):
                    encode2 = list(entry2.values())[0]
                    photo_id2 = list(entry2.keys())[0]

                    if photo_id2 in checked_ids:
                        continue

                    is_match = face_recognition.compare_faces([encode1], encode2)

                    if any(is_match):
                        photo_ids.add(photo_id2)
                        checked_ids.add(photo_id2)

                if len(photo_ids) >= 1:
                    # Если в множестве больше одного идентификатора, добавляем его в список совпадений
                    matches.append({True: photo_ids})

                checked_ids.update(photo_ids)  # Добавляем все идентификаторы в множество уже проверенных

            # Удаление списков, которые содержатся в других списках
            matches = [match for i, match in enumerate(matches) if
                       not any(match[True] < m[True] for m in matches[i + 1:])]

            return matches

        except Exception as e:
            print(e)
            return ''
