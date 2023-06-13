import flask
from flask import *
from src.auth.auth import current_user

from google.oauth2.credentials import Credentials

from dropbox.exceptions import AuthError
import dropbox
from dropbox import files, sharing

from src.app.config import *
from src.app.model import db, Photos, Users, PhotosMetaData, EditingPermission
from src.photos.DBHandler import DBHandler
from src.oauth2.oauth2 import authenticator

import asyncio

import src.photos.Get_photos_from_API

photos = Blueprint('photos', __name__, template_folder='../templates/photo_templates', static_folder='../static')

db_handler = DBHandler()

Get_photos_from_API = src.photos.Get_photos_from_API


@photos.route('/google_photos', methods=['GET', 'POST'])
def google_photos():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        try:
            credentials = Credentials.from_authorized_user_info(session['credentials'])

            if request.method == "POST":
                if 'next_page' in request.form:
                    next_page_token = request.form.get('next_page_token')
                    photos_data, next_page_token = Get_photos_from_API.photo_from_google(credentials, next_page_token)
                else:
                    photos_data, next_page_token = Get_photos_from_API.photo_from_google(credentials, None)
            else:
                photos_data, next_page_token = Get_photos_from_API.photo_from_google(credentials, None)

            user_photo_ids = [photo.photos_data for photo in Photos.query.filter().all()
                              if photo.service == '/photos/google_photos']
            if not photos_data:
                flash('No photo', 'info')
                return render_template('photo_templates/img.html', source_function=url_for('photos.google_photos'))
            for user_photo_id in user_photo_ids:
                for data in photos_data:
                    if user_photo_id == data['photoId']:
                        photos_data.remove(data)

            return render_template('photo_templates/img.html', base_url=photos_data,
                                   source_function=url_for('photos.google_photos'),
                                   next_page_token=next_page_token)
        except AuthError as e:
            print(e)
    return redirect(url_for('auth.login'))


@photos.route('/add_photo', methods=['GET', 'POST'])
def add_photo():
    if current_user.is_authenticated:
        if request.method == 'POST':
            photos_data = request.form.getlist('selected_photos')
            source_function = request.form.get('source_function')

            for photo_data in photos_data:
                photo = Photos(photos_data=photo_data, service=source_function, token=session['credentials']['token'],
                               refresh_token=session['credentials']['refresh_token'], user_id=current_user.id)
                db.session.add(photo)
            db.session.commit()
            return redirect(url_for('photos.user_photos'))
    return redirect(url_for('auth.login'))


@photos.route('/dropbox_photos', methods=['GET', 'POST'])
async def dropbox_photos():
    if current_user.is_authenticated:
        if 'access_token' not in session:
            authorize_url = authenticator.start_auth()
            return flask.redirect(authorize_url)
        try:
            dbx = dropbox.Dropbox(session['access_token'])

            if request.method == 'POST' and 'next_page' in request.form:
                cursor = session['cursor']
                if cursor:
                    files = await asyncio.to_thread(dbx.files_list_folder_continue, cursor)
                else:
                    return redirect(url_for('photos.dropbox_photos'))
            else:
                files = await asyncio.to_thread(dbx.files_list_folder, '', recursive=True, limit=10)

            base_url = []
            for entry in files.entries:
                if isinstance(entry, dropbox.files.FileMetadata) and entry.name.lower().endswith(
                        ('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    shared_links = await asyncio.to_thread(dbx.sharing_list_shared_links, path=entry.path_display)
                    if len(shared_links.links) > 0:
                        preview_url = shared_links.links[0].url.replace("?dl=0", "?raw=1")
                    else:
                        settings = dropbox.sharing.SharedLinkSettings(
                            requested_visibility=dropbox.sharing.RequestedVisibility.public)
                        shared_link = await asyncio.to_thread(dbx.sharing_create_shared_link_with_settings,
                                                              entry.path_display, settings)
                        preview_url = shared_link.url.replace("?dl=0", "?raw=1")
                    if preview_url:
                        base_url.append(preview_url)

            session['cursor'] = files.cursor

            if not files.has_more:
                session['cursor'] = None

            if not base_url:
                flash('No photo', 'info')
                return render_template('photo_templates/img.html', source_function=url_for('photos.dropbox_photos'))

            return render_template('photo_templates/img.html', base_url=base_url,
                                   source_function=url_for('photos.dropbox_photos'))

        except AuthError as e:
            print(e)

    return redirect(url_for('auth.login'))


@photos.route('/user_photos', methods=['GET', 'POST'])
def user_photos():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        current_user_family = Users.query.filter_by(parent_id=current_user.parent_id).all()
        photo_url = []
        family_users = []
        for family_user in current_user_family:
            family_user_photos = Photos.query.filter_by(user_id=family_user.id).all()
            correct_family_user_photos = []
            for photo in family_user_photos:
                photos_meta_data = PhotosMetaData.query.filter_by(photo_id=photo.id).first()
                if not photos_meta_data:
                    correct_family_user_photos.append(photo)
            photo_urls = db_handler.get_photos_from_db(correct_family_user_photos, session['credentials'])
            dict_photo_data = {family_user.email: photo_urls}
            family_users.append(family_user.email)
            photo_url.append(dict_photo_data)
        return render_template('photo_templates/user_photo.html', photos=photo_url,
                               parent_id=current_user.parent_id, family_users=family_users,
                               permissions=EditingPermission)
    else:
        return redirect(url_for('auth.login'))


@photos.route('/add_photo_description/<photo_id>', methods=['GET', 'POST'])
def add_photo_description(photo_id):
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))

        if request.method == "POST":

            title = request.form['title']
            description = request.form['description']
            location = request.form['location']
            creation_data = request.form['creation_date']

            photo_meta_data = PhotosMetaData.query.filter_by(photo_id=photo_id).first()

            if not photo_meta_data:
                new_photo_meta_data = PhotosMetaData(title=title, description=description,
                                                     location=location, creation_data=creation_data,
                                                     photo_id=photo_id)
                db.session.add(new_photo_meta_data)
                db.session.commit()
                flash('Photo add to tree successful')
            else:
                if title:
                    photo_meta_data.title = title
                if description:
                    photo_meta_data.description = description
                if location:
                    photo_meta_data.location = location
                if creation_data:
                    photo_meta_data.creation_data = creation_data

                db.session.commit()
                flash('Update successful')

            return redirect(url_for('photos.photos_tree'))

    else:
        return redirect(url_for('auth.login'))


@photos.route('/add_editing_permission/<photo_id>', methods=['GET', 'POST'])
def add_editing_permission(photo_id):
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        if request.method == "POST":
            photos_data = request.form.getlist('selected_users')
            for email in photos_data:
                user = Users.query.filter_by(email=email).first()
                permissions = EditingPermission(photo_id=photo_id, email=user.email, editable=True)
                db.session.add(permissions)
            db.session.commit()
        return redirect(url_for('photos.user_photos'))
    else:
        return redirect(url_for('auth.login'))


@photos.route('/photos_tree', methods=['GET', 'POST'])
def photos_tree():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        current_user_family = Users.query.filter_by(parent_id=current_user.parent_id).all()
        photo_data = []
        for family_user in current_user_family:
            family_user_photos = Photos.query.filter_by(user_id=family_user.id).all()
            photo_urls = db_handler.get_photos_from_db(family_user_photos, session['credentials'])
            for photo_id, url in photo_urls.items():
                photos_meta_data = PhotosMetaData.query.filter_by(photo_id=photo_id).first()
                if photos_meta_data:
                    photo_data.append({family_user.email: {photo_id: {'baseUrl': url,
                                                                      'title': photos_meta_data.title,
                                                                      'description': photos_meta_data.description,
                                                                      'location': photos_meta_data.location,
                                                                      'creation_data': photos_meta_data.creation_data}}})
        print(photo_data)
        return render_template('photo_templates/photos_tree.html', photo_data=photo_data, permissions=EditingPermission)
    else:
        return redirect(url_for('auth.login'))
