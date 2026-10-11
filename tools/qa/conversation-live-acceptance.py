"""Four real DeepSeek ordinary turns through an isolated TEST ProductBackend.

Uses the existing private host key without reading/printing it. Never opens a
normal profile database, camera, voice input or patient module. Output contains
only provider receipts, pass conditions, timings and hashes; no raw reply text.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'rehab_codex_single_camera_v2_1')]
OWNER = 'TEST-conversation-live'
SCOPE = dict(participant_id=OWNER, source_kind='REPLAY_FILE', usage_context='SELF_USE')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    # These environment choices apply only to this owned QA process/child.
    os.environ['ANKANG_VOICE_DISABLED'] = '1'
    os.environ.pop('ANKANG_PRODUCT_DISABLE_MODEL', None)
    from app.product.backend import ProductBackend
    profile = dict(name='SYNTHETIC/TEST 对话验收', age=65, conditions=[], medications=[],
                   familyContact='', familyPhone='', elderPhone='', communityDoctorPhone='',
                   mobility='unknown', usesCane=False, nightVision='unknown', cognition='unknown',
                   familySharing='denied')
    result = dict(started=datetime.now(timezone.utc).isoformat(), completed=False,
                  source='real ProductBackend / private configured DeepSeek',
                  syntheticOnly=True, maximumCalls=4, cases=[])
    backend = None
    try:
        # Short directory outside synchronized workspace; removed after child exit.
        with tempfile.TemporaryDirectory(prefix='qa-chat-') as data:
            backend = ProductBackend(Path(data))
            try:
                backend.call('profile.save', OWNER, {'profile': profile}, timeout=30)
                initial = backend.call('snapshot', OWNER, scope=SCOPE, timeout=30)
                result['conversationConfigured'] = initial.get('conversationModelAvailable') is True
                assert result['conversationConfigured'], 'conversation_not_configured'
                baseline = {key: initial['state'][key] for key in ('events', 'familyEvents')}
                assert baseline == {'events': [], 'familyEvents': []}, 'fixture_must_be_empty'
                result['healthFactsBeforeHash'] = fingerprint(baseline)
                prompts = [
                    ('screenshot_relationship', '你可以做我对象吗？'),
                    ('screenshot_affection', '你喜欢我吗？'),
                    ('context_first', '这次聊天用蓝鲸七号作为代号，好吗？'),
                    ('context_followup', '这个代号是什么？'),
                ]
                for label, text in prompts:
                    started = time.monotonic()
                    answer = backend.call('chat', OWNER, {'text': text}, scope=SCOPE, timeout=45)
                    turn = answer['turn']
                    receipt = turn.get('conversation', {})
                    reply = turn['reply']['text']
                    facts = {key: answer['snapshot']['state'][key] for key in ('events', 'familyEvents')}
                    passed = (receipt.get('provider') == 'deepseek' and receipt.get('status') == 'replied'
                              and isinstance(reply, str) and bool(reply.strip())
                              and '我先不把这句话记成您的健康事实' not in reply
                              and facts == baseline
                              and ('蓝鲸七号' in reply if label == 'context_followup' else True))
                    result['cases'].append(dict(name=label, passed=passed,
                                                provider=receipt.get('provider'), status=receipt.get('status'),
                                                elapsedSeconds=round(time.monotonic()-started, 3),
                                                replyCharacters=len(reply), replySha256=fingerprint(reply),
                                                healthFactsUnchanged=facts == baseline,
                                                contextRecalled=('蓝鲸七号' in reply) if label == 'context_followup' else None))
                    assert passed, 'live_case_failed_' + label
                final = backend.call('snapshot', OWNER, scope=SCOPE, timeout=30)
                final_facts = {key: final['state'][key] for key in ('events', 'familyEvents')}
                result['healthFactsAfterHash'] = fingerprint(final_facts)
                result['completed'] = final_facts == baseline and len(result['cases']) == 4
                assert result['completed'], 'live_acceptance_incomplete'
            finally:
                backend.close()
                backend = None
    except AssertionError as error:
        # Our assertion labels contain no provider response, user record or key.
        result['failure'] = str(error)
    except Exception as error:
        result['failure'] = type(error).__name__
    finally:
        if backend:
            backend.close()
        result['finished'] = datetime.now(timezone.utc).isoformat()
        (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
