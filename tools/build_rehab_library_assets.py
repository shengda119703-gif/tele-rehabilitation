"""Build public, read-only action cards; do not create clinical phase bindings.

Only the 656 explicitly selected illustrations are copied. Original PNGs,
archive variants, mapping proposals and private runtime files stay outside.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'mobile_rehab/static/assets/rehab-library-v1'
FIELDS = ('kind', 'category', 'category_label', 'region', 'level', 'introduction',
          'objective', 'equipment', 'start_conditions', 'preparation', 'instructions',
          'key_points', 'common_errors', 'source_dose', 'regression', 'progression',
          'stop_conditions', 'camera', 'observable', 'not_observable',
          'insufficient_observation', 'source_content', 'sequence_reuse', 'source_refs')


def build(destination=DEST):
    source = ROOT/'mobile_rehab/static/assets/rehab-candidates-v10'
    index = json.loads((source/'resource-index.json').read_text(encoding='utf-8'))
    catalogue_file = ROOT/'docs/rehab-library/image-handoff/catalogue.json'
    catalogue_bytes = catalogue_file.read_bytes()
    if hashlib.sha256(catalogue_bytes).hexdigest() != index['source_catalogue_sha256']:
        raise ValueError('Action source changed; revalidate selected illustrations')
    catalogue = json.loads(catalogue_bytes)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    images = {}
    for slot, item in index['images'].items():
        if not re.fullmatch(r'[0-9]{3}_[ET]-[A-Z]+-[0-9]{3}_(?:overview|s[0-9]{2})', slot):
            raise ValueError('Unexpected public illustration ID')
        path = source/(slot+'.webp')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item['display_sha256'] or item['file_status'] != 'present':
            raise ValueError('Selected illustration checksum mismatch: '+slot)
        shutil.copy2(path, destination/path.name)
        images[slot] = {'action_id': item['action_id'],
                        'url': '/static/assets/rehab-library-v1/'+path.name,
                        'sha256': digest, 'description': item.get('frame_description', ''),
                        'group_id': item.get('group_id', 'overview'),
                        'group_label': item.get('group_label', ''),
                        'review_status': item['review_status']}
    actions = []
    for card in catalogue['actions']:
        action = {field: card.get(field, '') for field in FIELDS}
        action.update(id=card['action_id'], name=card['action_name'],
                      overview=card['overview']['slot_id'],
                      steps=[s['slot_id'] for s in card['steps']],
                      pose_review_status=card['pose_review_status'])
        for slot in [action['overview'], *action['steps']]:
            if images[slot]['action_id'] != action['id']:
                raise ValueError('Cross-action illustration')
        actions.append(action)
    if len(actions) != 185 or len(images) != 656:
        raise ValueError('Incomplete public action library')
    result = {'version': 'public-action-library-1', 'scope': 'read_only_illustrations',
              'measurement_bindings': False, 'source_sha256': index['source_catalogue_sha256'],
              'categories': catalogue['categories'], 'actions': actions, 'images': images}
    (destination/'catalogue.json').write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':'))+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    data = build()
    print(json.dumps({'actions': len(data['actions']), 'illustrations': len(data['images']),
                      'measurement_bindings': False}))
