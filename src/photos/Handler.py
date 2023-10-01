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
                if not face.not_a_key:
                    if photo_id not in x:
                        x.append(photo_id)

                        family_user_faces.append({photo.photos_data: [face.photo_id, photo_ids[0]]})
            else:
                list_face_code.append({photo_id: [formatted_face_code.lower(), f'{photo_ids[0]}']})

    face_encode_handler.download_face_photos(session, family_user_faces, parent_id)

    return list_face_code


def add_relationship(tree, relationships):
    for rel in relationships:
        relative_id = rel.relative_id
        relationship_type = rel.relationship_type
        person_id = rel.person_id
        person_type = rel.person_type
        relative_name = Person.query.filter_by(id=relative_id).first()
        person_name = Person.query.filter_by(id=person_id).first()

        tree[relative_id]['Relationships'].append({
            'name': person_name.name,
            'id': person_id,
            'relationship': person_type
        })

        tree[person_id]['Relationships'].append({
            'name': relative_name.name,
            'id': relative_id,
            'relationship': relationship_type,
        })


def add_relationship_if_not_exists(person_id, new_relationship, tree):
    existing_relationships = tree[person_id]['Relationships']

    # Проверка на существование такого отношения
    for rel in existing_relationships:
        if rel['id'] == new_relationship['id'] and rel['relationship'] == new_relationship['relationship']:
            return

    # Если отношения нет, добавляем его
    existing_relationships.append(new_relationship)


def add_inverse_relationships(tree):
    for person_id, person_data in tree.items():
        person_gender = person_data.get('gender')

        for relationship in person_data['Relationships']:
            relative_id = relationship['id']
            relationship_type = relationship['relationship']

            if relationship_type in ['Father', 'Mother']:
                siblings = [rel for rel in tree[relative_id]['Relationships']
                            if rel['relationship'] in ['Son', 'Daughter'] and rel['id'] != person_id]

                for sibling in siblings:
                    add_relationship_if_not_exists(person_id, {
                        'name': sibling['name'],
                        'id': sibling['id'],
                        'relationship': 'Brother' if tree[sibling['id']]['gender'] == 'M' else 'Sister',
                    }, tree)
                    add_relationship_if_not_exists(sibling['id'], {
                        'name': person_data['name'],
                        'id': person_id,
                        'relationship': 'Brother' if person_gender == 'M' else 'Sister',
                    }, tree)

            if relationship_type in ['Brother', 'Sister']:
                parents = [rel for rel in tree[relative_id]['Relationships'] if
                           rel['relationship'] in ['Father', 'Mother']]

                for parent in parents:

                    add_relationship_if_not_exists(person_id, {
                        'name': parent['name'],
                        'id': parent['id'],
                        'relationship': parent['relationship']
                    }, tree)
                    add_relationship_if_not_exists(parent['id'], {
                        'name': person_data['name'],
                        'id': person_id,
                        'relationship': 'Son' if person_gender == 'M' else 'Daughter'
                    }, tree)


def remove_invalid_sibling_relationships(family_tree, relationships_list):

    for relationship in relationships_list:
        person_id = relationship.person_id
        relative_id = relationship.relative_id
        line = relationship.line  # Получаем значение line, если оно есть

        if not line:  # Пропускаем отношения без line
            continue

        # Ищем родителей в дереве
        person = family_tree.get(person_id)
        if not person:
            continue

        mother_id = None
        father_id = None

        for rel in person.get('Relationships', []):
            if rel['relationship'] == 'Mother':
                mother_id = rel['id']
            elif rel['relationship'] == 'Father':
                father_id = rel['id']

        relative = family_tree.get(relative_id)
        if not relative:
            continue

        # Если line == 'Paternal', проверяем, не является ли mother родителем relative

        if line == 'Paternal' and mother_id:
            if any(rel['id'] == mother_id for rel in relative.get('Relationships', [])):
                for i in family_tree[person_id]['Relationships']:
                    if i['id'] == mother_id:
                        family_tree[person_id]['Relationships'] = [
                            rel for rel in family_tree[person_id]['Relationships'] if i != rel
                        ]
                for i in family_tree[mother_id]['Relationships']:
                    if i['id'] == person_id:
                        family_tree[mother_id]['Relationships'] = [
                            rel for rel in family_tree[mother_id]['Relationships'] if i != rel
                        ]

        # Если line == 'Maternal', проверяем, не является ли father родителем relative
        elif line == 'Maternal' and father_id:
            if any(rel['id'] == father_id for rel in relative.get('Relationships', [])):
                for i in family_tree[person_id]['Relationships']:
                    if i['id'] == father_id:
                        family_tree[person_id]['Relationships'] = [
                            rel for rel in family_tree[person_id]['Relationships'] if i != rel
                        ]
                for i in family_tree[father_id]['Relationships']:
                    if i['id'] == person_id:
                        family_tree[father_id]['Relationships'] = [
                            rel for rel in family_tree[father_id]['Relationships'] if i != rel
                        ]

    return family_tree  # Возвращаем измененный список отношений


