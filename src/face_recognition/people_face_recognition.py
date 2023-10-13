# import json
import os.path
import pickle

import flask
from flask import *
from src.auth.auth import current_user

from google.oauth2.credentials import Credentials

from dropbox.exceptions import AuthError
import dropbox
from dropbox import files, sharing

# from src.app.config import *
from src.app.model import db, Photos, Users, PhotosMetaData, EditingPermission, FaceEncode, Person
from src.photos.DBHandler import DBHandler
from src.face_recognition.FaceEncodeHandler import FaceEncodeHandler
from src.oauth2.oauth2 import authenticator
from src.app.Forms import UpdateForm, UpdateLocationForm, UpdateCreationDateForm, AddFaceName, AddFamilyMemberForm

import asyncio

import src.photos.Handler as Handler
# import json
from pyicloud import PyiCloudService
import keyring
from pyicloud.exceptions import PyiCloudNoStoredPasswordAvailableException, PyiCloudFailedLoginException

people_face = Blueprint('people', __name__, template_folder='../templates/photo_templates', static_folder='../static')

db_handler = DBHandler()

face_encode_handler = FaceEncodeHandler()


@people_face.route('/', methods=['GET', 'POST'])
def people():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        faces_directory = os.path.join(os.path.dirname(__file__), '..', '..', 'static',
                                       'img', 'user_photos', 'faces')
        current_user_family = Users.query.filter_by(parent_id=current_user.parent_id).all()
        face_encode_data = (FaceEncode.query.join(Photos, FaceEncode.photo_id == Photos.id)
                            .join(Users, Photos.user_id == Users.id).filter(Users.parent_id == current_user.parent_id).all())

        face_encode = []
        for family_user in current_user_family:
            people_face = FaceEncode.query.filter_by(user_id=family_user.id).all()
            for face in people_face:
                decoded_face = pickle.loads(face.face_encode)
                face_encode.append({face.photo_id: [decoded_face, face.face_code]})
        list_face_code = face_encode_handler.face_folders(face_encode)
        existing_files = [file for root, dirs, files in os.walk(faces_directory) for file in files]
        items_to_remove = []
        for i in list_face_code:
            for photo_id, path in i.items():
                person = Person.query.filter_by(face_code=path[1]).first()
                if not person:
                    new_person = Person()
                    new_person.face_code = path[1]
                    new_person.name = ''
                    db.session.add(new_person)
                    db.session.commit()
                else:
                    if person.name:
                        path.append(person.name)
                    else:
                        path.append('')
        for face in face_encode_data:
            if f'{face.face_code}.jpeg' not in existing_files:
                # folder_path = os.path.join(faces_directory, path[0].split('/')[0])
                # items_to_remove.append(i)
                # face = FaceEncode.query.filter_by(face_code=path[1]).first()
                face.not_a_key = True
                db.session.commit()
                # if os.path.exists(folder_path):
                #     shutil.rmtree(folder_path)

        for item in items_to_remove:
            list_face_code.remove(item)
        session['list_face_code'] = list_face_code

        return render_template('photo_templates/people.html', face_dir=list_face_code)
    else:
        return redirect(url_for('auth.login'))


@people_face.route('/<face_code>', methods=['GET', 'POST'])
def one_face_people(face_code):
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        add_face_name = AddFaceName(request.form)
        add_family_member_form = AddFamilyMemberForm(request.form)

        people_name = FaceEncode.query.filter_by(face_code=face_code).first()
        person = Person.query.filter_by(face_code=face_code).first()
        current_user_family = Users.query.filter_by(parent_id=current_user.parent_id).all()
        face_encode = []

        for family_user in current_user_family:
            people_face = FaceEncode.query.filter_by(user_id=family_user.id).all()
            for face in people_face:
                decoded_face = pickle.loads(face.face_encode)
                face_encode.append({face.photo_id: [decoded_face, face.face_code]})
        face_encode_handler = FaceEncodeHandler()
        family_face_recognition = face_encode_handler.face_recognition_handler(face_encode)
        faces = []
        for i in family_face_recognition:
            family_user_photos = []
            for photo_id, photo_ids in i.items():
                if photo_ids[0] == face_code:
                    for j in photo_ids[1]:
                        family_user_photos.append(Photos.query.filter_by(id=j).first())
            faces.append(db_handler.get_photos_from_db(family_user_photos, session['credentials']))
        if request.method == 'POST' and add_face_name.validate_on_submit():
            person.name = add_face_name.face_name.data
            db.session.commit()
            return redirect(url_for('people.people'))

        for face in faces:
            for photo_id, data in face.items():
                photos_meta_data = PhotosMetaData.query.filter_by(photo_id=photo_id).first()
                if not photos_meta_data:
                    continue
                    # photos_data[photo_id] = {'baseUrl': data['baseUrl'],
                    #                          'title': 'Empty title',
                    #                          'description': data['description'],
                    #                          'location': 'Empty location',
                    #                          'creation_data': data['creationTime']}
                else:
                    data['title'] = photos_meta_data.title
                    data['description'] = photos_meta_data.description
                    data['location'] = photos_meta_data.location
                    data['creation_data'] = photos_meta_data.creation_data
                    # photos_data[photo_id] = {'baseUrl': data['baseUrl'],
                    #                          'title': photos_meta_data.title,
                    #                          'description': photos_meta_data.description,
                    #                          'location': photos_meta_data.location,
                    #                          'creation_data': photos_meta_data.creation_data}

        return render_template('photo_templates/one_face_people.html', faces=faces, add_face_name=add_face_name,
                               face_code=face_code, name=person.name,
                               add_family_member_form=add_family_member_form, list_face_code=session['list_face_code'],
                               face_path='/'.join([face_code[i:i+2] for i in range(0, len(face_code), 2)]))
    else:
        return redirect(url_for('auth.login'))
