from flask import url_for, render_template
from flask_jwt_extended import get_jwt_identity
from flask_restful import Resource, reqparse

from src.app.model import db, Message, User, UserMessage, Note, UserPerson, Photo
from src.app.utils import get_user_by_id
from src.auth.auth import send_email


class BaseComment(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('content', type=str, required=True, help="Content cannot be blank.")
    parser.add_argument('reply_user_email', type=str)
    parser.add_argument('id', type=str)

    def post(self, target_id, target_type):
        api_current_user = get_user_by_id(get_jwt_identity())
        args = self.parser.parse_args()
        content = args.get('content')
        reply_user_email = args.get('reply_user_email')

        # Получаем модель целевого объекта (Photo, Note, Relation) и его владельца
        target_model = self.get_target_model(target_type)
        target = target_model.query.get(target_id)
        if not target:
            return {'message': f'{target_model} not found'}, 404
        target_owner_id = self.get_target_owner_id(target)

        # Проверка разрешений для комментирования
        if api_current_user.id == target_owner_id and not reply_user_email:
            return {'message': f'You cannot leave a comment under your own {target_type}'}, 400
        if api_current_user.id != target_owner_id and reply_user_email:
            return {'message': 'You are not allowed to reply to this comment'}, 403

        recipient_id = User.query.filter_by(email=reply_user_email).first().id if reply_user_email else target_owner_id
        recipient_email = reply_user_email if reply_user_email else User.query.get(recipient_id).email

        # Общая логика создания и отправки комментария
        self.create_comment(api_current_user, recipient_id, content, target_id, target_type, recipient_email)
        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200

    def get(self, target_id, target_type):
        api_current_user = get_user_by_id(get_jwt_identity())

        target_model = self.get_target_model(target_type)
        target = target_model.query.get(target_id)
        if not target:
            return {'message': f'{target_model} not found'}, 404
        target_owner_id = self.get_target_owner_id(target)

        if api_current_user.id == target_owner_id:
            # Владелец фотографии видит все комментарии
            comments_query = UserMessage.query.filter_by(target_id=target_id, target_type=target_type)
        else:
            # Другие пользователи видят только свои комментарии и ответы владельца
            comments_query = UserMessage.query.filter_by(target_id=target_id, target_type=target_type).filter(
                (UserMessage.user_id == api_current_user.id) | (UserMessage.user_id == target_id)
            )

        comments = comments_query.all()
        comments_data = [
            {
                'comment_id': comment.message_id,
                'content': comment.content,
                'sender_id': comment.user_id,
                'timestamp': comment.timestamp,  # Или другой формат даты, если необходим
                'is_owner': True if comment.user_id == target_owner_id else False
            }
            for comment in comments
        ]

        return {'success': True, 'data': comments_data}, 200

    def put(self, target_id, target_type):
        api_current_user = get_user_by_id(get_jwt_identity())
        args = self.parser.parse_args()
        comment_id = args.get('id')
        new_content = args.get('content')

        # Получение комментария по ID
        user_message = UserMessage.query.filter_by(id=comment_id, user_id=api_current_user.id, target_id=target_id,
                                                   target_type=target_type).first()

        if not user_message:
            return {'message': 'Comment not found or you do not have permission to edit it'}, 404

        user_message.content = new_content
        db.session.commit()

        return {'success': True, 'data': {'message': 'Comment updated successfully', 'code': 200}}, 200

    def delete(self, target_id, target_type):
        api_current_user = get_user_by_id(get_jwt_identity())
        args = self.parser.parse_args()
        comment_id = args.get('id')

        user_message = UserMessage.query.filter_by(id=comment_id, target_id=target_id, target_type=target_type).first()
        if not user_message:
            return {'message': 'Comment not found'}, 404

        # Проверка, является ли текущий пользователь автором комментария или владельцем фотографии
        if user_message.user_id != api_current_user.id:
            target_model = self.get_target_model(target_type)
            target = target_model.query.get(target_id)
            if not target:
                return {'message': f'{target_model} not found'}, 404
            target_owner_id = self.get_target_owner_id(target)

            if target_owner_id != api_current_user.id:
                return {'message': 'You do not have permission to delete this comment'}, 403

        db.session.delete(user_message)
        db.session.commit()

        return {'success': True, 'data': {'message': 'Comment deleted successfully', 'code': 200}}, 200

    @staticmethod
    def get_target_model(target_type):
        # Возвращает класс модели в зависимости от типа цели
        if target_type == 'photo':
            return Photo
        elif target_type == 'note':
            return Note
        elif target_type == 'relation':
            return UserPerson
        else:
            raise ValueError('Invalid target type')

    @staticmethod
    def get_target_owner_id(target):
        # Возвращает ID владельца цели в зависимости от типа цели
        if isinstance(target, Photo):
            return target.user_id
        elif isinstance(target, Note):
            return target.author_id
        elif isinstance(target, UserPerson):
            return target.author_id
        else:
            raise ValueError('Invalid target instance')

    @staticmethod
    def create_comment(user, recipient_id, content, target_id, target_type, recipient_email):
        new_message = Message(sender_id=user.id, recipient_id=recipient_id)
        db.session.add(new_message)
        db.session.flush()

        user_message = UserMessage(user_id=user.id, message_id=new_message.id, content=content,
                                   target_id=target_id,
                                   target_type=target_type)
        db.session.add(user_message)

        db.session.commit()

        message = "New Comment Notification" if not recipient_email else "New Reply Notification"
        body = render_template('emails/comments/new_comment_notification.html'
                               if not recipient_email else 'emails/comments/new_reply_notification.html',
                               email=user.email if not recipient_email else recipient_email,
                               item_type=target_type,
                               content=content,
                               item_url=url_for('photos.one_photo', photo_id=target_id, _external=True))

        send_email(
            recipient_email,
            message,
            body
        )
