from src.app.model import Person


class FamilyTree:

    def add_relationship(self, tree, relationships):
        for rel in relationships:
            relative_id = rel.relative_id
            relationship_type = rel.relationship_type
            person_id = rel.person_id
            person_type = rel.person_type
            relative_name = Person.query.filter_by(id=relative_id).first()
            person_name = Person.query.filter_by(id=person_id).first()

            tree[relative_id]['relationships'].append({
                'name': person_name.name,
                'id': person_id,
                'relationship': person_type,
                "relation_id": rel.id
            })

            tree[person_id]['relationships'].append({
                'name': relative_name.name,
                'id': relative_id,
                'relationship': relationship_type,
                "relation_id": rel.id
            })
        self.add_inverse_relationships(tree, relationships)
        return tree

    @staticmethod
    def add_relationship_if_not_exists(person_id, new_relationship, tree):
        existing_relationships = tree[person_id]['relationships']

        # Проверка на существование такого отношения
        for rel in existing_relationships:
            if rel['id'] == new_relationship['id'] and rel['relationship'] == new_relationship['relationship']:
                return

        # Если отношения нет, добавляем его
        existing_relationships.append(new_relationship)

    def add_inverse_relationships(self, tree, relationships):
        for person_id, person_data in tree.items():
            person_gender = person_data.get('gender')

            for relationship in person_data['relationships']:
                relative_id = relationship['id']
                relationship_type = relationship['relationship']

                if relationship_type in ['Father', 'Mother']:
                    siblings = [rel for rel in tree[relative_id]['relationships']
                                if rel['relationship'] in ['Son', 'Daughter'] and rel['id'] != person_id]

                    for sibling in siblings:
                        self.add_relationship_if_not_exists(person_id, {
                            'name': sibling['name'],
                            'id': sibling['id'],
                            'relationship': 'Brother' if tree[sibling['id']]['gender'] == 'M' else 'Sister',
                        }, tree)
                        self.add_relationship_if_not_exists(sibling['id'], {
                            'name': person_data['name'],
                            'id': person_id,
                            'relationship': 'Brother' if person_gender == 'M' else 'Sister',
                        }, tree)

                if relationship_type in ['Brother', 'Sister']:
                    parents = [rel for rel in tree[relative_id]['relationships'] if
                               rel['relationship'] in ['Father', 'Mother']]

                    for parent in parents:
                        self.add_relationship_if_not_exists(person_id, {
                            'name': parent['name'],
                            'id': parent['id'],
                            'relationship': parent['relationship']
                        }, tree)
                        self.add_relationship_if_not_exists(parent['id'], {
                            'name': person_data['name'],
                            'id': person_id,
                            'relationship': 'Son' if person_gender == 'M' else 'Daughter'
                        }, tree)

        self.remove_invalid_sibling_relationships(tree, relationships)

    @staticmethod
    def remove_invalid_sibling_relationships(tree, relationships):

        for relationship in relationships:
            person_id = relationship.person_id
            relative_id = relationship.relative_id
            line = relationship.line  # Получаем значение line, если оно есть

            if not line:  # Пропускаем отношения без line
                continue

            # Ищем родителей в дереве
            person = tree.get(person_id)
            if not person:
                continue

            mother_id = None
            father_id = None

            for rel in person.get('relationships', []):
                if rel['relationship'] == 'Mother':
                    mother_id = rel['id']
                elif rel['relationship'] == 'Father':
                    father_id = rel['id']

            relative = tree.get(relative_id)
            if not relative:
                continue

            # Если line == 'Paternal', проверяем, не является ли mother родителем relative

            if line == 'Paternal' and mother_id:
                if any(rel['id'] == mother_id for rel in relative.get('relationships', [])):
                    for i in tree[person_id]['relationships']:
                        if i['id'] == mother_id:
                            tree[person_id]['relationships'] = [
                                rel for rel in tree[person_id]['relationships'] if i != rel
                            ]
                    for i in tree[mother_id]['relationships']:
                        if i['id'] == person_id:
                            tree[mother_id]['relationships'] = [
                                rel for rel in tree[mother_id]['relationships'] if i != rel
                            ]

            # Если line == 'Maternal', проверяем, не является ли father родителем relative
            elif line == 'Maternal' and father_id:
                if any(rel['id'] == father_id for rel in relative.get('relationships', [])):
                    for i in tree[person_id]['relationships']:
                        if i['id'] == father_id:
                            tree[person_id]['relationships'] = [
                                rel for rel in tree[person_id]['relationships'] if i != rel
                            ]
                    for i in tree[father_id]['relationships']:
                        if i['id'] == person_id:
                            tree[father_id]['relationships'] = [
                                rel for rel in tree[father_id]['relationships'] if i != rel
                            ]
