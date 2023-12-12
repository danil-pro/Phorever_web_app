from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError
from flask import redirect, url_for
from src.app.config import *
import random
import string
# from src.app.model import Photos, FaceEncode, Person
# from src.face_recognition.FaceEncodeHandler import FaceEncodeHandler
from datetime import datetime
from openai import OpenAI


def photo_from_google(credentials, page_token=None, limit=100):
    photos_data = []
    try:
        service = build(API_SERVICE_NAME, API_VERSION, credentials=credentials, static_discovery=False)
        results = service.mediaItems().list(
            pageSize=limit,
            pageToken=page_token,
            # fields='nextPageToken,mediaItems(id,baseUrl,mediaMetadata)',
        ).execute()
        items = results.get('mediaItems', [])
        for item in items:
            media_meta_data = item.get('mediaMetadata')
            video = media_meta_data.get('video')
            date = media_meta_data.get('creationTime')
            date_obj = datetime.fromisoformat(date[:-1])
            timestamp = date_obj.timestamp()
            description = item.get('description')
            if not video:
                photo_data = {'baseUrl': item.get('baseUrl'), 'photoId': item.get('id'),
                              'creationTime': timestamp,
                              'description': description if description else ''}

                photos_data.append(photo_data)
        next_page_token = results.get('nextPageToken')
    except HttpError as error:
        print(f"An error occurred: {error}")
        return [], None
    except RefreshError:
        return redirect(url_for('oauth2.google_authorize'))
    return photos_data, next_page_token


def openai_for_history(person_information, person_information_on_photo):
    client = OpenAI(api_key=OPENAI_API_KEY)

    completion = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system",
             "content": "Нужно только из данной информации написать историю о человеке."
                        "Всегда переводи unix time в нормальную дату дд/мм/гггг"
                        "В person_information могут присутствовать ключи: "
                        "name, last_name, birth_date, death_date, birth_place, notes. "
                        "birth_date и death_date это unix time переводи их в нормальную дату дд/мм/гггг "
                        " При создании истории вставаляй информацию"
                        " в хронологическом порядке."
                        " Не добавляй информацию от себя."
                        " Отвечай на языке который чаще всего встречается в тектсте"
                        " Перед частями истории пиши год когда это произошло"},
            {"role": "user",
             "content":
                 f" person_information: {person_information},"}
        ]
    )
    completion2 = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system",
             "content": "Дополни history используя информацию из полей person_information_on_photo"},
            {"role": "user",
             "content":
                 f" history: {completion.choices[0].message.content},"
                 f" person_information_on_photo: {person_information_on_photo}"}
        ]
    )
    return completion2.choices[0].message.content
