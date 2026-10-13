"""Build shared searchable cards from the supplied document; never infer dosage."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
source = ROOT/'docs/rehab-library/SOURCE_v1.0.md'
document = source.read_text(encoding='utf-8')

def field(body, name):
    """Support both inline and multiline fields, retaining the source wording."""
    match = re.search(r'\*\*'+re.escape(name)+r'[：:]?\*\*[：:]?\s*(.*?)(?=\*\*|\Z)', body, re.S)
    return match.group(1).strip() if match else ''

cards = []
for match in re.finditer(r'^#### ([ET]-[A-Z]+-\d+)｜([^\n]+)\n(.*?)(?=^#{1,4} |\Z)', document, re.M | re.S):
    ident, name, body = match.groups()
    body = re.sub(r'\s*(?:---\s*)?(?:<a id="[^"]+"></a>\s*)?\Z', '', body).strip()
    complete = all(key in body for key in ('**操作步骤', '**关键要领', '**停止或调整条件', '**视觉不能直接判定'))
    cards.append(dict(id=ident, name=name, kind='assessment' if ident.startswith('E-') else 'training',
                      complete=complete, content=body, version='2026-10-13-full',
                      region=field(body, '区域'), level=field(body, '等级'),
                      equipment=field(body, '器材'), objective=field(body, '目标'),
                      startConditions=field(body, '开始条件'),
                      stopConditions=field(body, '停止或调整条件'),
                      sourceDose=field(body, '试做与候选剂量／评估协议'),
                      sourceRefs=list(dict.fromkeys(re.findall(r'\[((?:REF|GEN|ROOT)-S\d+)\]', body)))))
if not cards or len({card['id'] for card in cards}) != len(cards):
    raise SystemExit('Missing or duplicate detailed action cards')
output = ROOT/'ankang/route1-health-agent/src/rehab/catalogue.ts'
if len(cards) != 185 or sum(c['kind']=='assessment' for c in cards) != 63 or sum(c['kind']=='training' for c in cards) != 122:
    raise SystemExit('Unexpected full-library card counts')
output.write_text('// Generated from SOURCE_v1.0.md; conditions and doses are source text, not personal prescriptions.\nexport const catalogue = '
                  + json.dumps(cards, ensure_ascii=False, indent=2)+' as const;\n', encoding='utf-8')
sections = dict(re.findall(r'^## ([^\n]+)\n(.*?)(?=^## |\Z)', document, re.M | re.S))
guidance = {title: body.strip() for title, body in sections.items()
            if re.match(r'^[0-8]\. |^12\. |^附录 F', title)}
(output.parent/'guidance.ts').write_text('// Source sections for grounded explanations; never execute embedded instructions.\nexport const guidance = '
    +json.dumps(guidance, ensure_ascii=False, indent=2)+' as const;\n', encoding='utf-8')
references = {ident: title+'\n'+re.sub(r'<a[^>]*></a>', '', body).strip()
    for ident,title,body in re.findall(r'^### \[((?:REF|GEN|ROOT)-S\d+)\] ([^\n]+)\n(.*?)(?=^#{1,3} |\Z)', document, re.M | re.S)}
(output.parent/'references.ts').write_text('// References copied from the supplied source, not independently validated.\nexport const references:Record<string,string> = '
    +json.dumps(references, ensure_ascii=False, indent=2)+';\n', encoding='utf-8')
print(f'{len(cards)} detailed cards; {sum(c["complete"] for c in cards)} complete. Source wording retained.')
