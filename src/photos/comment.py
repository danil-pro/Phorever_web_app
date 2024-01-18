from flask import Blueprint, request, redirect, url_for
from src.app.model import db, Message, User, UserMessage, PhotoMetaData
from src.auth.auth import current_user, send_email
from src.app.Forms import AddCommentForm
from flask_restful import Api, Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity

comment = Blueprint('comment', __name__, template_folder='../templates/photo_templates', static_folder='../static')
api = Api()


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


class Comment(Resource):

    @jwt_required()
    def post(self, photo_id):
        api_current_user = User.query.filter_by(id=get_jwt_identity()).first()

        args = comment_data.parse_args()

        content = args.get('content')
        recipient_user = User.query.filter_by(email=args.get('reply_user_email')).first()

        photo = PhotoMetaData.query.filter_by(photo_id=photo_id).first()

        sender_id = api_current_user.id
        recipient_id = photo.photo.user_id

        if sender_id == recipient_id:
            return {'message': 'You cannot leave a comment under your photo'}, 400

        if recipient_user:
            sender_id = photo.photo.user_id
            recipient_id = recipient_user.id

        new_message = Message(sender_id=sender_id, recipient_id=recipient_id, content=content, photo_id=photo_id)
        db.session.add(new_message)
        db.session.commit()

        sender_user = User.query.filter_by(id=sender_id).first()
        photo_owner = User.query.filter_by(id=photo.photo.user_id).first()

        send_email(recipient_user.email if recipient_user else photo_owner.email, '', f'''
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
        user_message = UserMessage(user_id=sender_id, message_id=new_message.id)
        db.session.add(user_message)

        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200


api.add_resource(Comment, '/api/v1/comment/<photo_id>')
