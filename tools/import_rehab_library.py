"""Build shared searchable cards from the supplied document; never infer dosage."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
source = ROOT/'docs/rehab-library/SOURCE_PARTIAL_v1.0.md'
cards = []
for match in re.finditer(r'^#### ([ET]-[A-Z]+-\d+)｜([^\n]+)\n(.*?)(?=^#### |\Z)', source.read_text(encoding='utf-8'), re.M | re.S):
    ident, name, body = match.groups()
    complete = all(key in body for key in ('**操作步骤', '**关键要领', '**停止或调整条件', '**视觉不能直接判定'))
    cards.append(dict(id=ident, name=name, kind='assessment' if ident.startswith('E-') else 'training',
                      complete=complete, content=body.strip(), version='2026-10-13-partial', dose=None))
if not cards or len({card['id'] for card in cards}) != len(cards):
    raise SystemExit('Missing or duplicate detailed action cards')
output = ROOT/'ankang/route1-health-agent/src/rehab/catalogue.ts'
output.write_text('// Generated from the preserved partial source; do not invent missing cards.\nexport const catalogue = '
                  + json.dumps(cards, ensure_ascii=False, indent=2)+' as const;\n', encoding='utf-8')
print(f'{len(cards)} detailed cards; {sum(c["complete"] for c in cards)} complete. No inferred training dosage.')
