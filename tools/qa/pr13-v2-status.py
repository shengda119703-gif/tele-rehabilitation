"""Regenerate the exact historical 77 nodes plus V2 UX nodes, without inheriting PASS.

Run from the repository root. Evidence files are reports from real test runs;
unit/SQLite evidence must not be promoted to model, browser or device evidence.
"""
import json
from collections import Counter
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / 'docs/validation/PR13_FULL_ACCEPTANCE_2026-10-17.md'
CONTRACT = ROOT / 'docs/architecture/REHAB_AGENT_V2_IMPLEMENTATION_2026-10-19.md'
OUT = ROOT / 'docs/validation/pr13-v2-evidence'


def generate():
    table = BASELINE.read_text(encoding='utf-8').split('## B. ')[1].split('## C. ')[0]
    nodes = []
    for line in table.splitlines():
        cells = [c.strip() for c in line.strip('|').split(' | ')]
        if len(cells) != 6 or cells[4] not in {'PASS', 'PARTIAL', 'NOT IMPLEMENTED', 'FAIL', 'UNVERIFIED'}:
            continue
        ident, _, title = cells[0].partition(' ')
        nodes.append(dict(id=ident, title=title, source=cells[1], entry=cells[2],
            baseline_status=cells[4], baseline_evidence=cells[3], baseline_limit=cells[5],
            status='UNVERIFIED', evidence=[], unresolved='尚未完成当前版本逐项复验；历史结果不继承为本轮 PASS。'))
    assert len(nodes) == 77, f'Expected exactly 77 original rows, got {len(nodes)}'
    assert len({n['id'] for n in nodes}) == 77
    for line in CONTRACT.read_text(encoding='utf-8').splitlines():
        if line.startswith('- UX'):
            ident, title = line[2:].split('：', 1)
            nodes.append(dict(id=ident, title=title, source=str(CONTRACT.relative_to(ROOT)).replace('\\','/'),
                entry='尚待实际客户端集成验收', baseline_status=None, baseline_evidence=None,
                status='UNVERIFIED', evidence=[], unresolved='当前没有本轮全链路验收证据。'))
    assert len(nodes) == 89
    updates = {
        '5.4': ('PARTIAL', 'AI 自然语言入口恢复真实检索、模型候选与校验；未完成持久化审核采用。', ['agent-ci.txt']),
        '4B.2': ('PARTIAL', '动作检索结果已完整回传 sourceRefs；尚无本轮真实模型口语覆盖。', ['agent-ci.txt']),
        '6.3': ('PARTIAL', '模型编造剂量现被拒绝；个体适用性与剂量专业审批尚未连接。', ['agent-ci.txt']),
        '6.4': ('PARTIAL', '既有规则候选审核已绑定内容摘要、资料及授权版本，持久化审核人回执；尚未连接 AI 草案。', ['cloud-tests.txt', 'review-tests.txt']),
        '9.2': ('PARTIAL', '已有两个显式技术动作映射；完整动作覆盖与采用链路未完成。', ['agent-ci.txt']),
        'UX07': ('PARTIAL', '候选入口不逐条输出工具事件，规则状态改为自然语言；尚无实际浏览器验收。', ['agent-ci.txt']),
        'UX04': ('PARTIAL', '云端修改个人条件使候选和旧核对失效；自然语言条件更新及候选修订未完成。', ['review-tests.txt']),
        'UX09': ('NOT IMPLEMENTED', 'AI 草案没有经专业批准、患者确认、实际采用及重读链路。', []),
        'UX12': ('NOT IMPLEMENTED', '核心 AI 草案→审核→采用→患者重开仍缺连接；不将单元测试称为端到端通过。', []),
        '11.2': ('PARTIAL', '新增本地持久任务、原话证据、修订版与器材追问；尚未完成可信限制解析和专业审核版本连接。', ['agent-ci.txt']),
        'UX02': ('PARTIAL', '缺器材时仅追问一个问题，补充后推进同一任务；更广的信息缺口尚待实现。', ['agent-ci.txt']),
        'UX05': ('PARTIAL', '任务取消、换话题、隐私、来源切换及30分钟过期清理；权限变化尚未贯通全部客户端。', ['agent-ci.txt']),
        'UX01': ('NOT IMPLEMENTED', '尚未实现本轮 V2 首次欢迎与可忽略的快捷提问。', []),
        'UX03': ('NOT IMPLEMENTED', '未接可信个人资料 reader，不能宣称已有可靠记录免重复追问。', []),
    }
    # These nodes specify deterministic guards/local business APIs, not live
    # model quality or UI adoption. Evidence scope is deliberately explicit.
    deterministic = ['1.2','1.4','1.5','2.3','2.4','3.6','3.7','4B.1','4B.3','4C.1','4C.2','4D.1',
                     '6.1','6.2','6.5','7.7','8.2','8.3','10.1','10.2','10.3','10.4','11.3','11.4']
    sqlite = ['4A.1','4A.2','7.3','7.4','7.8','7.9','7.10','9.5','REG.1']
    for ident in deterministic:
        updates[ident] = ('PASS', '限定本地确定性规则/Mock 模型边界；本轮完整 agent CI 已复跑，不扩大为真实模型或界面验收。', ['agent-ci.txt'])
    for ident in sqlite:
        updates[ident] = ('PASS', '本轮真实隔离 SQLite 与 Node/Python 桥接回归通过；模型为明确的本地协议 fixture，不是 DeepSeek 质量验收。', ['host-tests.txt','host-junit.xml'])
    for ident in ['3.2','3.4','4A.3','4D.2','4D.3','7.5','7.6','8.4','9.1','9.3','9.4','10.5','UI.4']:
        updates[ident] = ('NOT IMPLEMENTED', '当前源码仍未接通本节点要求的业务链路；详见检查点及原清单限定，不以安全拒绝记为功能通过。', [])
    for node in nodes:
        if node['id'] in updates:
            node['status'], node['unresolved'], node['evidence'] = updates[node['id']]
        if node['id'] == '11.2':
            node['source'] = 'R/src/rehab/taskState.ts, R/src/runtime/session.ts, ports.ts'
            node['entry'] = 'Session → executeSemanticTurn → taskUserText → runRehabWorkflow'
        elif node['id'] == '9.2':
            node['source'] = 'R/src/rehab/exerciseMapping.ts'
            node['entry'] = 'runRehabWorkflow → mapKnowledgeActionToApp'
        elif node['id'] == '6.4':
            node['source'] = 'cloud_service/rehab_workflow.py'
            node['entry'] = 'POST rehab-candidates/{id}/review（现有规则候选，非AI草案）'
    result = dict(schema='pr13-v2-acceptance-1', baseline=str(BASELINE.relative_to(ROOT)).replace('\\','/'),
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_scope='source_head 为本轮源码提交；源码与证据 SHA256 见 run-manifest.json。报告提交不会改变已测源码。',
        complete=False, merge_recommended=False, nodes=nodes)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'status.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines = ['# PR13 V2 当前逐项验收状态', '', '工程未完成，不建议合并 main。历史状态和本轮状态分列；未继承历史 PASS。', '',
        f"源码基准：`{result['source_head']}`；运行及源码摘要见 `run-manifest.json`。", '',
        '| ID | 节点 | 历史 | 当前 | 源码／入口 | 本轮证据 | 未解决问题 |', '|---|---|---|---|---|---|---|']
    for n in nodes:
        values=[n['id'],n['title'],n['baseline_status'] or '新增',n['status'],
            n['source']+' / '+n['entry'],', '.join(n['evidence']) or '无',n['unresolved']]
        lines.append('| '+' | '.join(v.replace('|','/').replace('\n',' ') for v in values)+' |')
    lines += ['', '原 77 项当前统计：`'+json.dumps(dict(Counter(n['status'] for n in nodes[:77])),ensure_ascii=False)+'`',
              '', 'UX01–UX12 当前统计：`'+json.dumps(dict(Counter(n['status'] for n in nodes[77:])),ensure_ascii=False)+'`', '']
    (OUT/'STATUS.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'Generated {len(nodes[:77])} original nodes and {len(nodes[77:])} UX nodes; complete=False')


if __name__ == '__main__':
    generate()
