import datetime
import os.path
import pickle
import subprocess

from flask import *
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Api, Resource, reqparse

from src.app.Forms import AddFaceName, AddFamilyMemberForm
from src.app.config import *
from src.app.model import db, Photo, User, PhotoMetaData, FaceEncode, Person, Note, Bio
from src.auth.auth import current_user
from src.face_recognition.FaceEncodeHandler import face_folders
from src.oauth2.oauth2 import check_credentials
from src.photos.DBHandler import DBHandler
from src.app.utils import family_access_required, get_user_by_id
from openai import OpenAI
from gtts import gTTS
from mutagen.mp3 import MP3


from io import BytesIO
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import requests


people_face = Blueprint('people', __name__, template_folder='../templates/photo_templates', static_folder='../static')

db_handler = DBHandler()

api = Api()


def people_init_app(app):
    api.init_app(app)


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

        return render_template('/person_template/people.html', face_dir=list_face_code)
    else:
        return redirect(url_for('auth.login'))


@people_face.route('/<face_code>', methods=['GET', 'POST'])
def one_face_people(face_code):
    if current_user.is_authenticated:
        add_face_name = AddFaceName(request.form)
        add_family_member_form = AddFamilyMemberForm(request.form)

        face_encode_data = (FaceEncode.query.join(Photo, FaceEncode.photo_id == Photo.id)
                            .join(User, Photo.user_id == User.id).filter(
            User.parent_id == current_user.parent_id).all())

        face_encode = [
            {face.photo_id: [pickle.loads(face.face_encode), face.face_code]}
            for face in face_encode_data
        ]

        list_face_code = face_folders(face_encode)

        faces = [Photo.query.filter_by(id=face.photo_id).first()
                 for face in FaceEncode.query.filter_by(key_face=face_code).all()]

        if request.method == 'POST' and add_face_name.validate_on_submit():
            person = Person.query.filter_by(face_code=face_code).first()
            if person is not None:
                person.name = add_face_name.face_name.data
                db.session.commit()
                return redirect(url_for('people.people'))
            else:
                return {'message': 'person is not exist'}

        person_name = Person.query.filter_by(face_code=face_code).first()

        return render_template('person_template/one_face_people.html', faces=faces, add_face_name=add_face_name,
                               face_code=face_code, name=person_name.name,
                               add_family_member_form=add_family_member_form, list_face_code=list_face_code,
                               face_path='/'.join([face_code[i:i+2] for i in range(0, len(face_code), 2)]))
    else:
        return redirect(url_for('auth.login'))


# @people_face.route('/bio/<face_code>', methods=['GET', 'POST'])
# def bio(face_code):
#     if current_user.is_authenticated:
#         face_code_lower = face_code.lower()
#         face_dir = [face_code_lower[i:i + 2] for i in range(0, len(face_code_lower), 2)]
#         save_path = os.path.join(face_dir[0], face_dir[1], face_dir[2], f"{face_code}.mp3")
#
#         person = Person.query.filter_by(face_code=face_code).first()
#         bio = []
#         if not person.bio:
#             flash("hui")
#             return redirect(url_for("people.one_face_people", face_code=face_code))
#         for i in person.bio:
#             photo = Photo.query.filter_by(id=i.photo_id).first()
#             bio.append({'text_content': i.text_content, 'photo_url': photo.photo_url if photo else None})
#         gtts(face_code)
#         return render_template('person_template/bio.html', bio=bio, sound=save_path)
#     else:
#         return redirect(url_for('auth.login'))


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
                             'notes': person.note})
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
    @family_access_required
    def get(self, face_code):

        api_current_user = get_user_by_id(get_jwt_identity())

        person = Person.query.filter_by(face_code=face_code).first()
        if not person:
            return {'message': "person is not exist"}, 404

        credentials = check_credentials(get_jwt_identity())
        db_handler.get_photos_from_db(api_current_user, credentials)
        photos = [Photo.query.filter_by(id=face.photo_id).first()
                  for face in FaceEncode.query.filter_by(key_face=face_code).all()]

        person_data = {
            "name": person.name,
            "last_name": person.last_name,
            "birth_date": person.birth_date,
            "death_date": person.death_date,
            "birth_place": person.birth_place,
            "note": [
                {
                    "id": note.id,
                    "author": note.author.email,
                    "date": note.date,
                    "note": note.note
                } for note in person.note
            ],
            "photos": [
                {
                    photo.id: {
                        'photo_url': photo.photo_url,
                        'title': photo.meta_data.title if photo.meta_data else None,
                        'description': photo.meta_data.description if photo.meta_data else None,
                        'location': photo.meta_data.location if photo.meta_data else None,
                        'creation_data': photo.meta_data.creation_data if photo.meta_data else None
                    }
                } for photo in photos
            ]
        }
        return {'success': True, 'data': {'person': person_data,
                                          'message': 'OK', 'code': 200}}, 200

    @jwt_required()
    @family_access_required
    def post(self, face_code):
        api_current_user = User.query.filter_by(id=get_jwt_identity()).first()
        person = Person.query.filter_by(face_code=face_code).first()
        args = current_person.parse_args()
        if args.get('birth_date') and args.get('death_date'):
            if args.get('birth_date') >= args.get('death_date'):
                return {'message': 'Date of birth and date of death cannot be in that order'}, 404
        elif args.get('death_date') and not person.birth_date:
            return {'message': 'Date of birth is required when providing a date of death'}, 400
        if person is not None:
            attributes = ['name', 'last_name', 'birth_date', 'death_date', 'birth_place', 'notes']
            for attr in attributes:
                value = args.get(attr)
                if value:
                    if attr == 'notes':
                        for note in value:
                            # Проверяем, что длина заметки не превышает 500 символов
                            if len(note['note']) > 500:
                                return {'message': 'The note is too big, please reduce its length.'}, 400

                            try:
                                # Попытка преобразовать Unix timestamp в объект datetime
                                datetime.datetime.utcfromtimestamp(note['date'])
                            except (TypeError, OverflowError, ValueError):
                                # В случае ошибок возвращаем False
                                return {"message": "date must be a UNIX timestamp"}, 400
                            except KeyError:
                                return {"error": "KeyError"}, 400

                            new_note = Note(
                                person_id=person.id,
                                author_id=api_current_user.id,
                                date=note['date'],
                                note=note['note']
                            )

                            # Добавляем заметку в сессию базы данных для последующего сохранения
                            db.session.add(new_note)

                        # Подтверждаем изменения в базе данных
                        db.session.commit()

                    else:
                        setattr(person, attr, value)
            db.session.commit()
            return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200
        else:
            return {'message': 'person is not exist'}, 404


class PersonBio(Resource):
    @jwt_required()
    @family_access_required
    def post(self, face_code):
        api_current_user = User.query.filter_by(id=get_jwt_identity()).first()
        person_information = {}
        person_information_on_photo = []
        person_photos = FaceEncode.query.filter_by(key_face=face_code).all()

        for i in person_photos:
            photo = Photo.query.filter_by(id=i.photo_id).first()

            title = photo.meta_data.title if photo.meta_data.title else "Unknown"
            description = photo.meta_data.description if photo.meta_data.description else "No description"
            location = photo.meta_data.location if photo.meta_data.location else "Unknown location"
            creation_time = datetime.datetime.fromtimestamp(photo.meta_data.creation_data).strftime(
                '%Y-%m-%d') if photo.meta_data.creation_data else "Unknown time"
            person_information_on_photo.append({'title': title,
                                                'description': description,
                                                'location': location,
                                                'creation_time': creation_time,
                                                'photo_id': photo.id})

        person = Person.query.filter_by(face_code=face_code).first()
        if person:
            person_information['name'] = person.name if person.name else None
            person_information['last_name'] = person.last_name if person.last_name else None
            person_information['birth_date'] = datetime.datetime.fromtimestamp(person.birth_date).strftime(
                '%Y-%m-%d') if person.birth_date else None
            person_information['death_date'] = datetime.datetime.fromtimestamp(person.death_date).strftime(
                '%Y-%m-%d') if person.death_date else None
            person_information['birth_place'] = person.birth_place if person.birth_place else None
            person_notes = Note.query.filter_by(person_id=person.id).all()
            if person_notes:
                person_information['note'] = []
                for note in person_notes:
                    # Определяем автора заметки, предпочитая имя, если оно доступно
                    if note.author.person:
                        author_name = note.author.person.name
                    else:
                        author_name = note.author.email if note.author.email else api_current_user.email

                    # Преобразуем дату из unix time
                    formatted_date = datetime.datetime.fromtimestamp(note.date).strftime('%Y-%m-%d')

                    # Добавляем информацию о заметке в список заметок
                    person_information['note'].append({
                        'note': note.note,
                        'author': author_name,
                        'date': formatted_date
                    })
            else:
                person_information['note'] = "No notes"

            if not person_information:
                return {'message': 'There is no information about the person'}

            history = self.openai_for_history(person_information, person_information_on_photo)
            bio = json.loads(history)
            print(bio)
            for part in bio['bio']:
                event = part['event']
                text_content = part['text_content']
                photo_id = part['photo_id'] if part['photo_id'] else None

                new_part = Bio(
                    event=event,
                    text_content=text_content,
                    photo_id=photo_id,
                    person_id=person.id
                )

                db.session.add(new_part)

            db.session.commit()
        else:
            return {'message': 'person is not exist'}, 404

        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200

    @jwt_required()
    @family_access_required
    def get(self, face_code):

        person = Person.query.filter_by(face_code=face_code).first()
        bio = []
        if not person.bio:
            return {'message': 'This biography has not yet been created'}, 404
        for i in person.bio:
            photo = Photo.query.filter_by(id=i.photo_id).first()
            bio.append({'text_content': i.text_content, 'photo_url': photo.photo_url if photo else None})
        sound = self.gtts(face_code)
        return {'success': True, 'data': {'bio': bio, 'sound': sound, 'code': 200}}, 200

    @staticmethod
    def openai_for_history(person_information, person_information_on_photo):
        client = OpenAI(api_key=OPENAI_API_KEY)

        completion = client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system",
                 "content": '''Given the provided personal information and photos metadata, generate a vivid and detailed biography in JSON format. Each section of the biography should contain rich, expressive text content that vividly brings to life the subject's life events, personality, and emotions. The 'text_content' field for each event should not exceed 500 characters. When a photo significantly complements a life event, include its metadata by assigning a relevant 'photo_id' from the photos_information. Ensure the biography is in chronological order and structured as an array of sections.

                                Demonstrate with examples by assigning a non-zero 'photo_id' for each section, even if a perfect match isn't available from the photos_information. Use the language most often found in the notes and photo metadata for the story. The 'photo_id' field must be filled; if the photo data does not perfectly match the note, assign any 'photo_id' available in photos_information. Integrate all available notes and photo metadata into the story, at least mentioning all notes.

                                In the 'event' field, include a name for each part of the story derived from the received data, ensuring the 'event' name does not exceed 50 characters. Ensure that 'photo_id' is presented as a separate numeric element and not included in the text content. Avoid using technical information in the text.

                                Example of expected output format:

                                {
                                  "bio": [
                                    {
                                      "event": "Event Name",
                                      "text_content": "Detailed text describing the event, personality, and emotions, ensuring it is rich and expressive.",
                                      "photo_id": 1
                                    },
                                    {
                                      "event": "Next Event",
                                      "text_content": "Text content for the next event, also vivid and detailed.",
                                      "photo_id": 2
                                    }
                                    // More sections following the same structure
                                  ]
                                }
                                Please adapt the request as needed to fulfill these specifications."
                        '''
                 },
                {"role": "user",
                 "content": f"person_information: {person_information}"},
                {"role": "user",
                 "content": f"photos_information: {person_information_on_photo}"},

            ]
        )

        return completion.choices[0].message.content

    @staticmethod
    def gtts(face_code):
        face_code_lower = face_code.lower()
        face_dir = [face_code_lower[i:i + 2] for i in range(0, len(face_code_lower), 2)]
        save_path = os.path.join(faces_dir, face_dir[0], face_dir[1], face_dir[2], f"{face_code}.mp3")
        if not os.path.exists(save_path):
            person = Person.query.filter_by(face_code=face_code).first()
            bio = []
            for part in person.bio:
                bio.append(part.text_content)
            audio = gTTS(text=''.join(bio), lang="en", slow=False)
            audio.save(save_path)
        return save_path


class Video(Resource):
    @jwt_required()
    @family_access_required
    def post(self, face_code):
        api_current_user = User.query.filter_by(id=get_jwt_identity()).first()

        face_code_lower = face_code.lower()
        face_dir = [face_code_lower[i:i + 2] for i in range(0, len(face_code_lower), 2)]
        video_save_path = os.path.join(faces_dir, face_dir[0], face_dir[1], face_dir[2],
                                       f"{face_code}.mp4")
        person = Person.query.filter_by(face_code=face_code).first()
        if person:

            videos = self.create_video(face_code=face_code, history=person.bio, user=api_current_user)

            inputs = ''.join([f'-i "{video}" ' for video in videos])

            # Команда для объединения видео
            command = f'ffmpeg {inputs} -filter_complex ' + \
                      '"[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=' + \
                      f'{len(videos)}:v=1:a=1[outv][outa]" -map "[outv]" -map "[outa]" {video_save_path}'

            # Запуск команды
            subprocess.run(command, shell=True, check=True)
            for video in videos:
                if os.path.exists(video):
                    os.remove(video)

        else:
            return {'message': 'person is not exist'}, 404

        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200

    @jwt_required()
    @family_access_required
    def get(self, face_code):
        # api_current_user = User.query.filter_by(id=get_jwt_identity()).first()

        face_code_lower = face_code.lower()
        face_dir = [face_code_lower[i:i + 2] for i in range(0, len(face_code_lower), 2)]
        video_path = os.path.join(faces_dir, face_dir[0], face_dir[1], face_dir[2],
                                       f"{face_code}.mp4")
        if video_path:
            return {'success': True, 'data': {'video': video_path, 'code': 200}}, 200
        else:
            return {'message': 'video is not exist'}, 404

    @staticmethod
    def textsize(text, font):
        im = Image.new(mode="P", size=(0, 0))
        draw = ImageDraw.Draw(im)
        _, _, width, height = draw.textbbox((0, 0), text=text, font=font)
        return width, height

    def create_video(self, history, face_code, user):

        videos = []
        face_code_lower = face_code.lower()
        credentials = check_credentials(user.id)
        face_dir = [face_code_lower[i:i + 2] for i in range(0, len(face_code_lower), 2)]
        slide_width, slide_height = (800, 450)

        count = 1
        for part in history:
            sound_save_path = os.path.join(faces_dir, face_dir[0], face_dir[1], face_dir[2],
                                           f"sound_{face_code}_{count}.mp3")
            audio = gTTS(text=part.text_content, lang="en", tld='us', slow=False)
            audio.save(sound_save_path)

            slide = Image.new('RGB', (slide_width, slide_height), color=(255, 255, 255))
            draw = ImageDraw.Draw(slide)
            font_size = 40  # Укажите размер шрифта
            font = ImageFont.truetype(f'{FONTS}/Roboto-Italic.ttf', font_size)
            shadow_size = 10

            if part.photo_id:
                photo = Photo.query.filter_by(id=part.photo_id).first()
                response = requests.get(photo.photo_url)
                db_handler.get_photos_from_db(user, credentials, update=True)
                image = Image.open(BytesIO(response.content))

                max_image_size = (400, 300)
                image.thumbnail(max_image_size)
                img_width, img_height = image.size
                img_x = (slide_width - img_width) // 2
                img_y = (slide_height - img_height) // 2 - 50  # Поднять фотографию выше центра

                # Создаем изображение для тени с альфа-каналом
                shadow_image = Image.new('RGBA', (img_width + shadow_size, img_height + shadow_size),
                                         color=(0, 0, 0, 0))
                shadow_draw = ImageDraw.Draw(shadow_image)
                shadow_color = (0, 0, 0, 150)  # Полупрозрачный черный цвет для тени

                # Рисуем прямоугольник на тени с зазором, равным shadow_size // 2
                shadow_draw.rectangle((
                    (shadow_size // 2, shadow_size // 2),
                    (img_width + shadow_size // 2, img_height + shadow_size // 2)
                ), fill=shadow_color)

                # Применяем размытие к тени
                shadow_image = shadow_image.filter(ImageFilter.GaussianBlur(radius=5))

                # Накладываем тень на слайд
                slide.paste(shadow_image, (img_x - shadow_size // 2, img_y - shadow_size // 2), shadow_image)

                # Накладываем изображение на слайд поверх тени
                slide.paste(image, (img_x, img_y))
            wrapped_text = textwrap.fill(part.event, width=40)

            text_width, text_height = self.textsize(wrapped_text, font=font)

            # Вычисление позиции текста (центрирование текста ниже фотографии)
            text_x = (slide_width - text_width) // 2
            text_y = img_y + img_height + 10  # Отступ текста ниже фотографии

            # Рисование текста на слайде
            draw.text((text_x, text_y), wrapped_text, fill="black", font=font)

            slide_save_path = os.path.join(faces_dir, face_dir[0], face_dir[1], face_dir[2],
                                           f"slide_{face_code}_{count}.png")
            video_save_path = os.path.join(faces_dir, face_dir[0], face_dir[1], face_dir[2],
                                           f"video_{face_code}_{count}.mp4")
            slide.save(slide_save_path)
            videos.append(video_save_path)
            count += 1

            audio = MP3(sound_save_path)
            duration = round(audio.info.length)

            # Команда для создания видео из одного слайда с продолжительностью аудио
            command = [
                'ffmpeg',
                '-y',  # Перезаписывать выходной файл, если он существует
                '-loop', '1',  # Зациклить входное изображение
                '-i', slide_save_path,  # Входной файл (изображение)
                '-i', sound_save_path,  # Входной файл (аудио)
                '-c:v', 'libx264',  # Кодек видео
                '-t', str(duration),  # Длительность видео
                '-pix_fmt', 'yuv420p',  # Формат пикселей
                '-vf', 'scale=1280:720',  # Масштабирование видео
                video_save_path  # Выходной файл
            ]

            subprocess.run(command, check=True)

            if os.path.exists(slide_save_path):
                os.remove(slide_save_path)
            if os.path.exists(sound_save_path):
                os.remove(sound_save_path)

        return videos


class BindUserToPerson(Resource):
    @jwt_required()
    @family_access_required
    def post(self, face_code):
        user = User.query.filter_by(id=get_jwt_identity()).first()
        person = Person.query.filter_by(face_code=face_code).first()
        user.person_id = person.id
        db.session.commit()
        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200


api.add_resource(Peoples, '/api/v1/people')
api.add_resource(BindUserToPerson, '/api/v1/people/bind_person/<face_code>')
api.add_resource(People, '/api/v1/people/<face_code>')
api.add_resource(PersonBio, '/api/v1/people/bio/<face_code>')
api.add_resource(Video, '/api/v1/people/video/<face_code>')
