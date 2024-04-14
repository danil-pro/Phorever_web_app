from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request
from src.app.model import db, Permission, Photo, UserPerson, User  # Импортируйте вашу модель базы данных
from src.app.utils import get_user_by_id, send_email
from flask import render_template, url_for


class BasePermission(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('users', type=list, action="append", help='users is required', required=True)

    @jwt_required()
    def post(self, target_id, target_type):
        api_current_user = get_user_by_id(get_jwt_identity())
        args = request.get_json()
        emails = args.get('users')
        target_model = self.get_target_model(target_type)
        target = target_model.query.get(target_id)
        if not target:
            return {'message': f'This {target_type} does not exist'}, 403
        target_owner_id = self.get_target_owner_id(target)

        if target_owner_id != api_current_user.id:

            permission = Permission.query.filter_by(target=target_type, target_id=target_id,
                                                    email=api_current_user.email, editable=True).first()
            if not permission:
                return {'message': f'You do not have permission to edit this {target_type}'}, 403

        for email in emails:
            user = User.query.filter_by(email=email).first()
            if user:
                permission = Permission.query.filter_by(target=target_type, target_id=target_id,
                                                        email=user.email).first()
                if permission:
                    return {'message': 'User already has permission'}, 403

                new_permission = Permission(target=target_type, target_id=target_id, email=user.email, editable=True)
                db.session.add(new_permission)

                message = "New Permission Notification"
                body = render_template("emails/permission/permission.html",
                                       email=user.email,
                                       target=target_type,
                                       item_url=url_for('photos.one_photo', photo_id=target_id, _external=True)
                                       if target_type == "photo" else
                                       url_for('family_tree.family_tree_relationships', _external=True),
                                       grantor_email=api_current_user.email)

                send_email(user.email, message, body)

            else:
                return {'message': f'User {email} does not exist'}, 404
        db.session.commit()
        return {'success': True, 'data': {'message': 'OK', 'code': 200}}, 200

    @jwt_required()
    def get(self, target_id, target_type):
        api_current_user = get_user_by_id(get_jwt_identity())
        target_model = self.get_target_model(target_type)
        target = target_model.query.get(target_id)
        if not target:
            return {'message': f'{target_model} not found'}, 404

        target_owner_id = self.get_target_owner_id(target)

        target_owner = User.query.filter_by(id=target_owner_id).first()
        if not target_owner:
            return {'message': f'{target_type} owner not found'}, 404

        # Проверяем, совпадает ли parent_id у текущего пользователя и у владельца фото
        if api_current_user.parent_id != target_owner.parent_id:
            return {'message': 'You do not have access to view permissions for this photo'}, 403

        permissions = Permission.query.filter_by(target=target_type, target_id=target_id).all()
        permissions_list = [{'email': permission.email, 'editable': permission.editable} for permission in permissions]

        return {'success': True, 'data': permissions_list, 'code': 200}, 200

    @jwt_required()
    def delete(self, target_id, target_type):
        api_current_user = get_user_by_id(get_jwt_identity())
        args = request.get_json()
        emails_to_remove = args.get('emails')  # Получаем список email-адресов для удаления

        if not isinstance(emails_to_remove, list):
            return {'message': 'Invalid data format: "emails" should be a list'}, 400

        target_model = self.get_target_model(target_type)
        target = target_model.query.get(target_id)
        if not target:
            return {'message': f'{target_model} not found'}, 404
        target_owner_id = self.get_target_owner_id(target)

        if target_owner_id != api_current_user.id:
            return {'message': 'You are not the owner of this relation'}, 403

        # Удаление разрешений для списка email-адресов
        permissions_removed = Permission.query.filter(
            Permission.target == target_type,
            Permission.target_id == target_id,
            Permission.email.in_(emails_to_remove)
        ).delete(
            synchronize_session=False)  # synchronize_session=False для оптимизации при удалении большого количества
        # записей

        if permissions_removed == 0:
            return {'message': 'No permissions found or already removed for the provided emails'}, 404

        db.session.commit()
        return {'success': True, 'message': f'Permissions removed successfully for {permissions_removed} users',
                'code': 200}, 200

    @staticmethod
    def get_target_model(target_type):
        if target_type == 'photo':
            return Photo
        elif target_type == 'relation':
            return UserPerson
        else:
            raise ValueError("Invalid target type")

    @staticmethod
    def get_target_owner_id(target):
        # Возвращает ID владельца цели в зависимости от типа цели
        if isinstance(target, Photo):
            return target.user_id
        elif isinstance(target, UserPerson):
            return target.author_id
        else:
            raise ValueError('Invalid target instance')
