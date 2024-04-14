from flask_jwt_extended import jwt_required
# import json
from flask_restful import Api

# from src.app.config import *
from src.permissions.BasePermission import BasePermission

api = Api()


def permission_init_app(app):
    api.init_app(app)


class PhotoPermission(BasePermission):
    @jwt_required()
    def post(self, target_id):
        return super().post(target_id, 'photo')

    @jwt_required()
    def get(self, target_id):
        return super().get(target_id, 'photo')

    @jwt_required()
    def delete(self, target_id):
        return super().delete(target_id, 'photo')


class RelationPermission(BasePermission):
    @jwt_required()
    def post(self, target_id):
        return super().post(target_id, 'relation')

    @jwt_required()
    def get(self, target_id):
        return super().get(target_id, 'relation')

    @jwt_required()
    def delete(self, target_id):
        return super().delete(target_id, 'relation')


api.add_resource(PhotoPermission, '/api/v1/photo/permission/<int:target_id>')
api.add_resource(RelationPermission, '/api/v1/family_tree/permission/<int:target_id>')
