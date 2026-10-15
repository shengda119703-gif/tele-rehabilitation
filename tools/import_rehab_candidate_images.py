"""Import explicitly selected public assets for internal, non-clinical previews.

Usage: python tools/import_rehab_candidate_images.py --handoff DIR --mapping CSV
Pillow is only needed for this offline import, never by the application runtime.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(handoff, mapping, repo):
    from PIL import Image
    source = handoff / 'docs/rehab-library/image-handoff'
    catalogue = json.loads((source / 'catalogue.json').read_text(encoding='utf-8'))
    target = repo / 'mobile_rehab/static/assets/rehab-candidates-v10'
    docs = repo / 'docs/rehab-library/candidate-images'
    target.mkdir(parents=True, exist_ok=True)
    (docs / 'cards').mkdir(parents=True, exist_ok=True)
    images = {}
    for item in catalogue['images']:
        relative = Path(item['image_path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        assert 'archive' not in relative.parts and 'references' not in relative.parts
        original = handoff / relative
        assert sha(original).lower() == item['sha256'].lower(), str(relative)
        slot = item['slot_id']
        assert slot not in images and all(c.isalnum() or c in '-_' for c in slot)
        display = target / (slot + '.webp')
        with Image.open(original) as im:
            im.load()
            assert im.size == (item['width'], item['height'])
            full = im.convert('RGB')
            full.thumbnail((1200, 1200))  # Entire frame; no crop, mirror or rotation.
            full.save(display, 'WEBP', quality=92, method=6)
            width, height = full.size
        images[slot] = {
            **item, 'original_path': item['image_path'],
            'original_sha256': item['sha256'].lower(),
            'url': '/static/assets/rehab-candidates-v10/' + display.name,
            'display_sha256': sha(display), 'display_width': width,
            'display_height': height, 'review_status': 'pending',
            'side': None, 'phase': None, 'side_review_status': 'pending',
            'phase_review_status': 'pending',
        }
    actions = []
    for action in catalogue['actions']:
        card = Path(action['source_card_path']).name
        (docs / 'cards' / card).write_bytes((source / 'cards' / card).read_bytes())
        actions.append({
            'action_id': action['action_id'], 'sequence': action['sequence'],
            'name': action['action_name'], 'category': action['category'],
            'kind': action['kind'], 'card_path': 'docs/rehab-library/candidate-images/cards/' + card,
            'card_sha256': sha(docs / 'cards' / card),
            'image_slots': [s for s, i in images.items() if i['action_id'] == action['action_id']],
            'review_status': 'pending',
        })
    mappings = {}
    with mapping.open(encoding='utf-8-sig', newline='') as f:
        rows = [r for r in csv.DictReader(f) if r['记录类型'] == '仓库阶段槽位']
    for row in rows:
        exercise = row['仓库动作ID']
        entry = mappings.setdefault(exercise, {
            'exercise_id': exercise, 'label': row['仓库动作名'], 'review_status': 'pending',
            'patient_enabled': False, 'candidate_images': [], 'issues': [],
            'phase_slots': {side: {phase: None for phase in ('start', 'move', 'return')}
                            for side in ('left', 'right')},
        })
        slot = row['候选图片槽位']
        if not slot:
            continue
        image = images[slot]
        assert image['image_path'] == row['候选资源路径']
        assert image['action_id'] == row['公共动作ID']
        relation = next((i for i in entry['candidate_images'] if i['slot_id'] == slot), None)
        if relation is None:
            relation = {'slot_id': slot, 'public_action_id': image['action_id'],
                        'side': None, 'phase': None, 'review_status': 'pending',
                        'proposed_targets': [], 'issues': []}
            entry['candidate_images'].append(relation)
        # Proposals are audit evidence, never runtime side/phase bindings.
        relation['proposed_targets'].append({'side': row['本人侧别目标'], 'phase': row['阶段目标']})
        issue = row['候选关系与限制']
        if issue not in relation['issues']:
            relation['issues'].append(issue)
        if issue not in entry['issues']:
            entry['issues'].append(issue)
    for entry in mappings.values():
        entry['preview_scope'] = 'resource_library_only' if any('阻断' in i for i in entry['issues']) else 'internal_candidate'
    assert len(actions) == 185 and len(images) == 656 and len(mappings) == 53
    assert sum(bool(m['candidate_images']) for m in mappings.values()) == 25
    index = {'schema_version': 1, 'package_version': '1.0',
             'default_review_status': 'pending', 'preview_only': True,
             'source_catalogue_sha256': sha(source / 'catalogue.json'),
             'mapping_source_sha256': sha(mapping), 'public_actions': actions, 'images': images}
    for name, data in [('resource-index.json', index), ('exercise-mapping.json', mappings)]:
        (target / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (docs / 'mapping-source.csv').write_bytes(mapping.read_bytes())
    for name in ('image_manifest.csv', 'steps.csv', 'actions.csv'):
        (docs / name).write_bytes((source / name).read_bytes())
    print(json.dumps({'actions': len(actions), 'images': len(images), 'mapped_candidates': 25,
                      'unmatched': 28, 'display_bytes': sum(p.stat().st_size for p in target.glob('*.webp'))}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff', type=Path, required=True)
    parser.add_argument('--mapping', type=Path, required=True)
    args = parser.parse_args()
    build(args.handoff.resolve(), args.mapping.resolve(), Path(__file__).resolve().parents[1])
