import os.path
import pickle

from flask import *
from src.auth.auth import current_user
from sqlalchemy.orm.attributes import flag_modified

from src.app.model import db, Photo, User, PhotoMetaData, FaceEncode, Person
from src.photos.DBHandler import DBHandler
from src.face_recognition.FaceEncodeHandler import download_face_photos, face_folders, face_recognition_handler
from src.oauth2.oauth2 import check_credentials
from src.app.Forms import AddFaceName, AddFamilyMemberForm
from src.photos.Handler import openai_for_history
from src.app.config import *
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Api, Resource, reqparse
import datetime

people_face = Blueprint('people', __name__, template_folder='../templates/photo_templates', static_folder='../static')

db_handler = DBHandler()


api = Api()


@people_face.route('/', methods=['GET', 'POST'])
def people():
    if current_user.is_authenticated:
        # print(current_user.person.name)

        current_user_family = User.query.filter_by(parent_id=current_user.parent_id).all()
        face_encode_data = (FaceEncode.query.join(Photo, FaceEncode.photo_id == Photo.id)
                            .join(User, Photo.user_id == User.id).filter(User.parent_id == current_user.parent_id).all())

        face_encode = []
        for family_user in current_user_family:
            people_face = FaceEncode.query.filter_by(user_id=family_user.id).all()
            for face in people_face:
                decoded_face = pickle.loads(face.face_encode)
                face_encode.append({face.photo_id: [decoded_face, face.face_code]})

        list_face_code = face_folders(face_encode)
        existing_files = [file for root, dirs, files in os.walk(faces_dir) for file in files]
        items_to_remove = []
        for data in list_face_code:
            person = Person.query.filter_by(face_code=data['face_code']).first()
            if not person:
                new_person = Person()
                new_person.face_code = data['face_code']
                new_person.name = ''
                db.session.add(new_person)
                db.session.commit()
            else:
                if person.name:
                    data.update({'person_name': person.name})
                else:
                    data.update({'person_name': ''})
        for face in face_encode_data:
            if f'{face.face_code}.jpeg' not in existing_files:
                face.not_a_key = True
                db.session.commit()

        for item in items_to_remove:
            list_face_code.remove(item)

        return render_template('photo_templates/people.html', face_dir=list_face_code)
    else:
        return redirect(url_for('auth.login'))


@people_face.route('/<face_code>', methods=['GET', 'POST'])
def one_face_people(face_code):
    if current_user.is_authenticated:
        credentials = check_credentials()
        add_face_name = AddFaceName(request.form)
        add_family_member_form = AddFamilyMemberForm(request.form)

        person = Person.query.filter_by(face_code=face_code).first()

        current_user_family = User.query.filter_by(parent_id=current_user.parent_id).all()
        face_encode = []

        for family_user in current_user_family:
            people_face = FaceEncode.query.filter_by(user_id=family_user.id).all()
            for face in people_face:
                decoded_face = pickle.loads(face.face_encode)
                face_encode.append({face.photo_id: [decoded_face, face.face_code]})
        family_face_recognition = face_recognition_handler(face_encode)
        list_face_code = face_folders(face_encode)
        for data in list_face_code:
            person_data = Person.query.filter_by(face_code=data['face_code']).first()
            if not person_data:
                return {'message': 'person is not exist'}
            else:
                if person_data.name:
                    data.update({'person_name': person_data.name})
                else:
                    data.update({'person_name': ''})
        faces = []
        for i in family_face_recognition:
            family_user_photos = []
            for photo_id, photo_ids in i.items():
                if photo_ids[0] == face_code:
                    for j in photo_ids[1]:
                        family_user_photos.append(Photo.query.filter_by(id=j).first())
            faces.append(db_handler.get_photos_from_db(family_user_photos, credentials))
        if request.method == 'POST' and add_face_name.validate_on_submit():
            if person is not None:
                person.name = add_face_name.face_name.data
                db.session.commit()
                return redirect(url_for('people.people'))
            else:
                return {'message': 'person is not exist'}

        for face in faces:
            for data in face:
                photos_meta_data = PhotoMetaData.query.filter_by(photo_id=data['photo_id']).first()
                if not photos_meta_data:
                    continue
                else:
                    data['title'] = photos_meta_data.title
                    data['description'] = photos_meta_data.description
                    data['location'] = photos_meta_data.location
                    data['creation_data'] = photos_meta_data.creation_data
        person_name = Person.query.filter_by(face_code=face_code).first()

        return render_template('photo_templates/one_face_people.html', faces=faces, add_face_name=add_face_name,
                               face_code=face_code, name=person_name.name,
                               add_family_member_form=add_family_member_form, list_face_code=list_face_code,
                               face_path='/'.join([face_code[i:i+2] for i in range(0, len(face_code), 2)]))
    else:
        return redirect(url_for('auth.login'))


class Peoples(Resource):
    @jwt_required()
    def get(self):
        api_current_user = User.query.filter_by(id=get_jwt_identity()).first()

        current_user_family = User.query.filter_by(parent_id=api_current_user.parent_id).all()
        face_encode_data = (FaceEncode.query.join(Photo, FaceEncode.photo_id == Photo.id)
                            .join(User, Photo.user_id == User.id).filter(
            User.parent_id == api_current_user.parent_id).all())

        face_encode = []
        for family_user in current_user_family:
            people_face = FaceEncode.query.filter_by(user_id=family_user.id).all()
            for face in people_face:
                decoded_face = pickle.loads(face.face_encode)
                face_encode.append({face.photo_id: [decoded_face, face.face_code]})
        list_face_code = face_folders(face_encode)
        existing_files = [file for root, dirs, files in os.walk(faces_dir) for file in files]
        items_to_remove = []
        for data in list_face_code:
            person = Person.query.filter_by(face_code=data['face_code']).first()
            if not person:
                new_person = Person()
                new_person.face_code = data['face_code']
                db.session.add(new_person)
                db.session.commit()
            else:
                data.update({'name': person.name,
                             'last_name': person.last_name,
                             'birth_date': person.birth_date,
                             'death_date': person.death_date,
                             'birth_place': person.birth_place,
                             'notes': person.notes})
        for face in face_encode_data:
            if f'{face.face_code}.jpeg' not in existing_files:
                face.not_a_key = True
                db.session.commit()

        for item in items_to_remove:
            list_face_code.remove(item)

        return {'success': True, 'data': {'faces': list_face_code,
                                          'message': 'OK', 'code': 200}}, 200


current_person = reqparse.RequestParser()
current_person.add_argument('name', type=str, required=False)
current_person.add_argument('last_name', type=str, required=False)
current_person.add_argument('birth_date', type=int, required=False)
current_person.add_argument('death_date', type=int, required=False)
current_person.add_argument('birth_place', type=str, required=False)
current_person.add_argument('notes', type=dict, action="append", required=False)


class People(Resource):
    @jwt_required()
    def get(self, face_code):
        api_current_user = User.query.filter_by(id=get_jwt_identity()).first()

        credentials = check_credentials(get_jwt_identity())
        current_user_family = User.query.filter_by(parent_id=api_current_user.parent_id).all()
        face_encode = []

        for family_user in current_user_family:
            people_face = FaceEncode.query.filter_by(user_id=family_user.id).all()
            for face in people_face:
                decoded_face = pickle.loads(face.face_encode)
                face_encode.append({face.photo_id: [decoded_face, face.face_code]})
        family_face_recognition = face_recognition_handler(face_encode)

        current_person_photos = []
        for i in family_face_recognition:
            family_user_photos = []
            for photo_id, photo_ids in i.items():
                if photo_ids[0] == face_code:
                    for j in photo_ids[1]:
                        family_user_photos.append(Photo.query.filter_by(id=j).first())
            result = db_handler.get_photos_from_db(family_user_photos, credentials)
            if result:
                current_person_photos.extend(result)
        for face in current_person_photos:
            photos_meta_data = PhotoMetaData.query.filter_by(photo_id=face['photo_id']).first()
            if not photos_meta_data:
                continue
            else:
                face['title'] = photos_meta_data.title
                face['description'] = photos_meta_data.description
                face['location'] = photos_meta_data.location
                face['creation_data'] = photos_meta_data.creation_data
        return {'success': True, 'data': {'current_person_photos': current_person_photos,
                                          'message': 'OK', 'code': 200}}, 200

    @jwt_required()
    def post(self, face_code):
        api_current_user = User.query.filter_by(id=get_jwt_identity()).first()
        person = Person.query.filter_by(face_code=face_code).first()
        args = current_person.parse_args()
        if args.get('birth_date') and args.get('death_date'):
            if args.get('birth_date') <= args.get('death_date'):
                return {'message': 'Date of birth and date of death cannot be in that order'}, 404
        elif args.get('death_date') and not person.birth_date:
            return {'message': 'Date of birth is required when providing a date of death'}, 400
        if person is not None:
            attributes = ['name', 'last_name', 'birth_date', 'death_date', 'birth_place', 'notes']
            for attr in attributes:
                value = args.get(attr)
                if value:
                    if attr == 'notes':
                        notes = person.notes or []

                        next_key = max([int(note.get('id', 0)) for note in notes], default=0) + 1

                        for note in value:
                            if len(note['note']) > 1000:
                                return {'message': 'The note is too big, please reduce its length.'}, 400
                            note['author'] = api_current_user.email
                            note['id'] = next_key
                            notes.append(note)
                            next_key += 1

                        # Обновляем атрибут 'notes' объекта 'person'
                        person.notes = notes
                        flag_modified(person, 'notes')

                        db.session.commit()

                    else:
                        setattr(person, attr, value)
            db.session.commit()
            return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200
        else:
            return {'message': 'person is not exist'}, 404

    @jwt_required()
    def put(self, face_code):

        user = User.query.filter_by(id=get_jwt_identity()).first()
        person = Person.query.filter_by(face_code=face_code).first()
        user.person_id = person.id
        db.session.commit()
        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200


class CreateHistory(Resource):
    def post(self, face_code):
        person_information = {}
        person_information_on_photo = []
        person_photos = FaceEncode.query.filter_by(key_face=face_code).all()
        for i in person_photos:
            person_photo_metadata = PhotoMetaData.query.filter_by(photo_id=i.photo_id).first()
            person_information_on_photo.append({'title': person_photo_metadata.title,
                                                'description': person_photo_metadata.description,
                                                'location': person_photo_metadata.location,
                                                'creation_time':
                                                    datetime.datetime.fromtimestamp(person_photo_metadata.creation_data)
                                               .strftime('%Y-%m-%d')})
        person = Person.query.filter_by(face_code=face_code).first()
        person_information['name'] = person.name
        person_information['last_name'] = person.last_name
        person_information['birth_date'] = datetime.datetime.fromtimestamp(person.birth_date).strftime('%Y-%m-%d')
        person_information['death_date'] = datetime.datetime.fromtimestamp(person.death_date).strftime('%Y-%m-%d')
        person_information['birth_place'] = person.birth_place
        person_information['notes'] = person.notes

        return {'history': f'{str(openai_for_history(person_information, person_information_on_photo))}'}


api.add_resource(Peoples, '/api/v1/people')
api.add_resource(People, '/api/v1/people/<face_code>')
api.add_resource(CreateHistory, '/api/v1/people/create_history/<face_code>')
