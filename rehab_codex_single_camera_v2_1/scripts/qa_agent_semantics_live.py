"""Opt-in real DeepSeek equivalence-class QA. Synthetic inputs, no store/camera.

This is a service test, not a substitute for human desktop acceptance.
No credentials or arbitrary provider bodies are written to the report.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.agent_conversation import ModelConfig
from app.agent_statements import StatementSession


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='Consent to send the synthetic cases to DeepSeek; may incur API cost')
    parser.add_argument('--model', default='deepseek-flash')
    parser.add_argument('--output', type=Path, default=ROOT/'qa-output'/'agent-a3-live.json')
    args = parser.parse_args()
    if not args.live or not os.environ.get('DEEPSEEK_API_KEY'):
        print('NOT RUN: real DeepSeek QA requires --live and DEEPSEEK_API_KEY in this process. No request made.')
        return 2
    config = ModelConfig('https://api.deepseek.com', args.model, os.environ['DEEPSEEK_API_KEY'], True).validate()
    scope = dict(participant_id='A3-LIVE-SYNTHETIC', source_kind='SYNTHETIC', usage_context='TEST')
    groups = {
        'new_report': ['我今天没胃口', '现在我没有食欲', '今天我没睡好'],
        'state_change': ['刚才发烧，现在好了', '现在已经不发烧了', '刚才的状况已经恢复了'],
        'correction': ['我刚才说错了，其实没有发烧', '上一条关于发烧的描述有误，请撤回', '纠正一下，我其实没有出现刚才描述的情况'],
    }
    reports = []
    def forbidden_store():
        raise AssertionError('The semantic service test must never open a store')
    for act, variants in groups.items():
        for text in variants:
            session = StatementSession(scope, forbidden_store)
            if act != 'new_report':
                seed = session.turn('我今天发烧', config=config)
                if not seed or not seed['proposed_actions']:
                    reports.append(dict(expected=act, text=text, passed=False, reason='seed_not_accepted'))
                    continue
            result = session.turn(text, config=config)
            relation = {'new_report':'none', 'state_change':'updates', 'correction':'corrects'}[act]
            passed = bool(result and result.get('dialogue_act') == act and result['understanding']
                          and any(c['relation']['type'] == relation for c in result['understanding'])
                          and result['proposed_actions'])
            reports.append(dict(expected=act, text=text, passed=passed,
                                actual=result.get('dialogue_act') if result else None,
                                status=result.get('extraction_status', 'grounded') if result else 'ordinary_dialogue'))
            print(f'{act}: {"PASS" if passed else "FAIL"}', flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(model=args.model, synthetic_only=True, cases=reports), ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{sum(r["passed"] for r in reports)}/{len(reports)} live cases passed. Human UI acceptance remains separate.')
    return 0 if all(r['passed'] for r in reports) else 1


if __name__ == '__main__':
    raise SystemExit(main())
