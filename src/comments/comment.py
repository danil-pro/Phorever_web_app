from flask import Blueprint, request, redirect, url_for
from flask_jwt_extended import jwt_required
from flask_restful import Api, reqparse

from src.app.Forms import AddCommentForm
from src.app.model import db, Message, User, UserMessage, PhotoMetaData
from src.auth.auth import current_user, send_email
from src.comments.BaseComment import BaseComment

comment = Blueprint('comment', __name__, template_folder='../templates/photo_templates', static_folder='../static')
api = Api()


def comment_init_app(app):
    api.init_app(app)


@comment.route('/post_comment/<photo_id>', methods=['POST'])
def post_comment(photo_id):
    form = AddCommentForm(request.form)
    photo = PhotoMetaData.query.filter_by(photo_id=photo_id).first()
    sender_id = current_user.id
    recipient_id = photo.photo.user_id
    recipient_user = User.query.filter_by(email=request.form.get('recipient_user', '').strip()).first()

    if recipient_user:
        sender_id = photo.photo.user_id
        recipient_id = recipient_user.id

    content = form.add_content.data

    # Создание нового сообщения
    new_message = Message(sender_id=sender_id, recipient_id=recipient_id, content=content, photo_id=photo_id)
    db.session.add(new_message)
    db.session.commit()

    sender_user = User.query.filter_by(id=sender_id).first()

    send_email(recipient_user.email if recipient_user else sender_user.email, '', f'''
    Hello,

    We wanted to let you know that {sender_user.email} has just left a comment on your photo titled 
    "{photo.title if photo.title else 'Empty title'}".
    
    Comment:
    {content}
    
    You can view the comment and respond by following this link:
    {url_for('photos.one_photo', photo_id=photo_id, _external=True)}
    
    Thank you for using our service!
    
    Best regards,
    Phorever

    ''')

    # Создание записи UserMessage для отправителя
    user_message_sender = UserMessage(user_id=sender_id, message_id=new_message.id)
    db.session.add(user_message_sender)

    return redirect(url_for('photos.one_photo', photo_id=photo_id))


comment_data = reqparse.RequestParser()
comment_data.add_argument("reply_user_email", type=str, required=False)
comment_data.add_argument("content", type=str, required=True)
comment_data.add_argument("comment_id", type=int, required=False)


class PhotoComment(BaseComment):
    @jwt_required()
    def post(self, target_id):
        return super().post(target_id, 'photo')

    @jwt_required()
    def get(self, target_id):
        return super().get(target_id, 'photo')

    @jwt_required()
    def put(self, target_id):
        return super().put(target_id, 'photo')

    @jwt_required()
    def delete(self, target_id):
        return super().delete(target_id, 'photo')
    # @jwt_required()


class NoteComment(BaseComment):
    @jwt_required()
    def post(self, target_id):
        return super().post(target_id, 'note')

    @jwt_required()
    def get(self, target_id):
        return super().get(target_id, 'note')

    @jwt_required()
    def put(self, target_id):
        return super().put(target_id, 'note')

    @jwt_required()
    def delete(self, target_id):
        return super().delete(target_id, 'note')


class RelationComment(BaseComment):
    @jwt_required()
    def post(self, target_id):
        return super().post(target_id, 'relation')

    @jwt_required()
    def get(self, target_id):
        return super().get(target_id, 'relation')

    @jwt_required()
    def put(self, target_id):
        return super().put(target_id, 'relation')

    @jwt_required()
    def delete(self, target_id):
        return super().delete(target_id, 'relation')


api.add_resource(PhotoComment, '/api/v1/photo/comment/<target_id>')
api.add_resource(NoteComment, '/api/v1/note/comment/<note_id>')
api.add_resource(RelationComment, '/api/v1/family_tree/comment/<relation_id>')
