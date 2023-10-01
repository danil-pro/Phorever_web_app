from flask import *
from src.auth.auth import current_user

from src.app.model import db, Photos, FaceEncode, Person, Relationship

from src.app.Forms import AddFamilyMemberForm

from src.family_tree.FamilyTree import FamilyTree


family_tree = Blueprint('family_tree', __name__,
                        template_folder='../templates/photo_templates', static_folder='../static')
family_tree_add_relationships = FamilyTree()


@family_tree.route('/', methods=['GET', 'POST'])
def family_tree_relationships():
    if current_user.is_authenticated:
        if 'credentials' not in session:
            return redirect(url_for('oauth2.google_authorize'))
        form = AddFamilyMemberForm(request.form)
        if request.method == "POST":
            relative_person = Person.query.filter_by(face_code=request.form['relative_person']).first()
            relationship = form.relationship.data
            person = Person.query.filter_by(face_code=request.form['person']).first()
            relationship_type = request.form['type1']
            person_type = request.form['type2']
            degree = None
            line = None
            if relationship == 'Sibling':
                degree = request.form.get('degree')
                if degree != 'Full':
                    line = request.form.get('line')

            # Проверка на уникальность отношения
            existing_relationship = Relationship.query.filter(
                (Relationship.person_id == person.id) & (Relationship.relative_id == relative_person.id) |
                (Relationship.person_id == relative_person.id) & (Relationship.relative_id == person.id)
            ).first()
            if existing_relationship:
                flash("Relationship already exists between these two people.")
                return redirect(url_for('people.people', face_code=person.face_code))

            # Проверка на максимальное количество родителей (если это родитель)
            if relationship in ["Parent"]:
                existing_parents = Relationship.query.filter_by(
                    person_id=person.id,
                    relationship_type=relationship
                ).count()
                if existing_parents >= 2:
                    flash("A person can only have two parents.")
                    return redirect(url_for('people.people', face_code=person.face_code))

            new_relationship = Relationship(
                relative_id=relative_person.id,
                relationship_type=relationship_type,
                person_id=person.id,
                person_type=person_type,
                degree=degree,
                line=line
            )
            db.session.add(new_relationship)

            db.session.commit()

        tree = {}

        persons = Person.query.join(FaceEncode).join(Photos).filter(Photos.user_id == current_user.parent_id).all()
        person_ids = [person.id for person in persons]
        relationships = Relationship.query.filter(Relationship.person_id.in_(person_ids)).all()

        id_to_name = {person.id: person.name if person.name else "not name" for person in persons}

        x = []
        for rel in relationships:
            person_name = id_to_name[rel.person_id]
            relative_name = id_to_name[rel.relative_id]
            if rel.person_id not in x:
                x.append(rel.person_id)

                tree[rel.person_id] = {'name': person_name, 'id': rel.person_id, 'Relationships': []}
                if 'gender' not in tree[rel.person_id]:
                    if rel.person_type in ['Sister', 'Daughter', 'Mother']:
                        tree[rel.person_id]['gender'] = 'F'
                    if rel.person_type in ['Brother', 'Son', 'Father']:
                        tree[rel.person_id]['gender'] = 'M'
            if rel.relative_id not in x:
                x.append(rel.relative_id)
                tree[rel.relative_id] = {'name': relative_name, 'id': rel.relative_id, 'Relationships': []}
                if 'gender' not in tree[rel.relative_id]:
                    if rel.relationship_type in ['Sister', 'Daughter', 'Mother']:
                        tree[rel.relative_id]['gender'] = 'F'
                    if rel.relationship_type in ['Brother', 'Son', 'Father']:
                        tree[rel.relative_id]['gender'] = 'M'

        return render_template('photo_templates/photos_tree.html',
                               family_tree=family_tree_add_relationships.add_relationship(tree, relationships))
    else:
        return redirect(url_for('auth.login'))