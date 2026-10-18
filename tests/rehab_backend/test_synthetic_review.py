"""Local review security/contract TEST data; no genuine operator signs here."""
from __future__ import annotations

import copy
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest

import av
import numpy as np

from tools.rehab_ml.synthetic import contracts as c
from tools.rehab_ml.synthetic import review as r
from tools.rehab_ml.synthetic.video import probe_video


class SyntheticReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'raw').mkdir()
        (self.root/'manifests').mkdir()
        source = self.root/'raw/one.mp4'
        with av.open(str(source), mode='w') as container:
            stream = container.add_stream('libx264', rate=8)
            stream.width, stream.height, stream.pix_fmt = 160, 96, 'yuv420p'
            for index in range(9):
                image = np.zeros((96, 160, 3), dtype=np.uint8)
                image[:] = [40+index*20, 170, 70]
                image[12:40, 8+index*10:32+index*10] = [240, 220, 40]
                frame = av.VideoFrame.from_ndarray(image, format='rgb24')
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        self.timeline = probe_video(source, timeline_path=self.root/'manifests/one-pts.json')
        self.sample = dict(sample_id='SECRET-pilot-person-A', source_group_id='SECRET-person',
            reference_group_id='SECRET-ref', lineage_ids=['SECRET-origin'], split='train', stage='pilot',
            scenario='A', exercise_id='shoulder_abduction', side='unknown', view='front', status='pending',
            video=dict(path=str(source), sha256=r._hash(source), width=160, height=96, frame_count=9,
                       timeline_path=str(self.root/'manifests/one-pts.json'),
                       timeline_sha256=r._hash(self.root/'manifests/one-pts.json')),
            generation=dict(prompt_version='TEST', seed=1, model_sha256='a'*64,
                            workflow_sha256='b'*64, prompt_sha256='c'*64, prompt='SECRET_NEVER_SHOW_PROMPT'))
        self.manifest = dict(schema_version=c.SCHEMA_VERSION, dataset_id='TEST-review',
                             split_freeze=None, samples=[self.sample])
        self.write_manifest()

    def write_manifest(self):
        (self.root/'manifests/dataset.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def store(self):
        store = r.ReviewStore(self.root)
        token = next(iter(store.tokens))
        return store, token

    def payload(self, store, token, *, role='human_operator', decision='accepted', known_zero=True):
        form = store.catalog()['samples'][0]['form']
        form.update(reviewer_id='TEST-only-operator-placeholder', reviewer_role=role,
                    side='left', side_mask=True)
        form['review']['full_video_watched'] = True
        if known_zero:
            form.update(observable_count=0, observable_count_mask=True)
        return dict(token=token, annotation=form, decision=decision,
                    reason='', playback_coverage=[[0., .5], [.5, 1.]])

    def test_prepare_returns_blank_unknowns_and_does_not_save_human_files(self):
        forms = r.prepare(self.root)
        self.assertEqual(len(forms), 1)
        self.assertIsNone(forms[0]['reviewer_id'])
        self.assertIsNone(forms[0]['observable_count'])
        self.assertFalse(forms[0]['review']['full_video_watched'])
        self.assertFalse((self.root/'annotations').exists())

    def test_catalog_blinds_names_scenarios_prompt_predictions_and_paths(self):
        store, token = self.store()
        catalog = store.catalog()
        text = json.dumps(catalog)
        for private in ('SECRET', 'scenario', 'generation', 'prompt', str(self.root), 'prediction'):
            self.assertNotIn(private, text)
        self.assertEqual(catalog['samples'][0]['form']['sample_id'], token)
        self.assertEqual(catalog['samples'][0]['presentation_s'], self.timeline['presentation_s'])

    def test_acceptance_binds_full_original_hash_frames_and_does_not_change_generator_manifest(self):
        store, token = self.store()
        before = (self.root/'manifests/dataset.json').read_bytes()
        result = store.submit(self.payload(store, token))
        self.assertTrue(result['eligible_for_training'])
        self.assertEqual((self.root/'manifests/dataset.json').read_bytes(), before)
        loaded = r.load_reviewed(self.root)
        self.assertEqual(len(loaded['eligible_annotations']), 1)
        reviewed = loaded['manifest']['samples'][0]
        self.assertEqual(reviewed['status'], 'accepted')
        self.assertEqual(reviewed['acceptance']['reviewed_video_sha256'], self.sample['video']['sha256'])
        self.assertEqual(reviewed['acceptance']['reviewed_frame_count'], 9)
        saved = list((self.root/'annotations').rglob('*.json'))
        record = json.loads(saved[0].read_text(encoding='utf-8'))
        self.assertFalse(record['reviewer_identity_is_verified'])
        self.assertFalse(record['playback_coverage_is_identity_proof'])

    def test_saves_always_create_versions_and_new_draft_does_not_reuse_old_approval(self):
        store, token = self.store()
        first = store.submit(self.payload(store, token))
        second = store.submit(self.payload(store, token, decision='pending', known_zero=False))
        self.assertNotEqual(first['version'], second['version'])
        self.assertEqual(len(list((self.root/'annotations').rglob('*.json'))), 2)
        loaded = r.load_reviewed(self.root)
        self.assertEqual(loaded['eligible_annotations'], [])
        self.assertEqual(loaded['manifest']['samples'][0]['status'], 'pending')

    def test_ai_draft_is_saved_but_cannot_approve_a_source(self):
        store, token = self.store()
        with self.assertRaisesRegex(ValueError, 'human_full_video'):
            store.submit(self.payload(store, token, role='ai_draft'))
        result = store.submit(self.payload(store, token, role='ai_draft', decision='pending'))
        self.assertFalse(result['eligible_for_training'])
        self.assertEqual(r.load_reviewed(self.root)['eligible_annotations'], [])

    def test_accept_requires_explicit_complete_viewing_and_reviewer_id(self):
        store, token = self.store()
        payload = self.payload(store, token)
        payload['annotation']['review']['full_video_watched'] = False
        with self.assertRaisesRegex(ValueError, 'human_full_video'):
            store.submit(payload)
        payload = self.payload(store, token)
        payload['annotation']['reviewer_id'] = None
        with self.assertRaises(c.SyntheticContractError):
            store.submit(payload)

    def test_save_calls_contracts_rejecting_zero_with_unknown_inventory_and_non_pts(self):
        store, token = self.store()
        payload = self.payload(store, token)
        payload['annotation']['repetitions'] = [c.repetition_template('TEST-rep')]
        with self.assertRaisesRegex(c.SyntheticContractError, 'unknown_completion_inventory'):
            store.submit(payload)
        payload = self.payload(store, token)
        payload['annotation']['phase_intervals'] = [dict(phase='outbound', start_s=.1, end_s=.5, label_mask=True)]
        with self.assertRaisesRegex(c.SyntheticContractError, 'phase_start'):
            store.submit(payload)

    def test_exclusion_requires_reason_and_keeps_zero_unknown(self):
        store, token = self.store()
        payload = self.payload(store, token, decision='excluded', known_zero=False)
        with self.assertRaisesRegex(ValueError, 'exclusion_reason'):
            store.submit(payload)
        payload['reason'] = 'TEST: observable frame discontinuity'
        self.assertFalse(store.submit(payload)['eligible_for_training'])
        loaded = r.load_reviewed(self.root)
        self.assertEqual(loaded['manifest']['samples'][0]['status'], 'excluded')
        self.assertIsNone(loaded['annotations'][0]['observable_count'])

    def test_payload_cannot_set_output_path_or_change_source(self):
        store, token = self.store()
        payload = self.payload(store, token)
        payload['output_path'] = '../unrelated.json'
        with self.assertRaisesRegex(ValueError, 'explicit_review_fields'):
            store.submit(payload)
        payload = self.payload(store, token)
        payload['annotation']['sample_id'] = self.sample['sample_id']
        with self.assertRaisesRegex(ValueError, 'token_must_match'):
            store.submit(payload)
        self.assertFalse((self.root/'annotations').exists())

    def test_manifest_video_and_timeline_must_be_inside_dataset_root(self):
        outside = Path(self.temp.name).parent/'not-this-dataset.mp4'
        self.sample['video']['path'] = str(outside)
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'outside_declared'):
            r.prepare(self.root)

    def test_changed_raw_or_index_is_rejected_at_submit(self):
        store, token = self.store()
        Path(self.sample['video']['timeline_path']).write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'timeline_changed|source_or_timeline_hash_changed'):
            store.submit(self.payload(store, token))

    def test_client_declared_coverage_must_remain_bounded(self):
        store, token = self.store()
        for coverage in ([[0., 100.]], [[1., 0.]], [[float('nan'), 1.]]):
            payload = self.payload(store, token)
            payload['playback_coverage'] = coverage
            with self.assertRaisesRegex(ValueError, 'coverage_outside'):
                store.submit(payload)

    def append_source(self):
        source = self.root/'raw/two.mp4'
        with av.open(str(source), mode='w') as container:
            stream = container.add_stream('libx264', rate=8)
            stream.width, stream.height, stream.pix_fmt = 160, 96, 'yuv420p'
            for index in range(9):
                image = np.full((96, 160, 3), [180, 30+index*15, 90], dtype=np.uint8)
                for packet in stream.encode(av.VideoFrame.from_ndarray(image, format='rgb24')):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        pts = probe_video(source, timeline_path=self.root/'manifests/two-pts.json')
        sample = copy.deepcopy(self.sample)
        sample.update(sample_id='SECRET-new-person-D', source_group_id='SECRET-new-person',
                      reference_group_id='SECRET-new-reference', lineage_ids=['SECRET-new-motion'])
        sample['video'].update(path=str(source), sha256=r._hash(source),
            timeline_path=pts['timeline_path'], timeline_sha256=pts['timeline_sha256'])
        self.manifest['samples'].append(sample)
        self.write_manifest()
        return sample

    def test_catalog_refresh_appends_real_video_and_preserves_old_tokens_and_csrf(self):
        store, token = self.store()
        initial = store.catalog()
        csrf = store.csrf
        old_form = copy.deepcopy(initial['samples'][0]['form'])
        new_sample = self.append_source()
        refreshed = store.catalog()
        self.assertEqual(len(refreshed['samples']), 2)
        self.assertEqual(store.csrf, csrf)
        self.assertEqual(refreshed['samples'][0]['token'], token)
        self.assertEqual(refreshed['samples'][0]['form'], old_form)
        self.assertEqual(store.media(token), Path(self.sample['video']['path']).resolve())
        new_token = refreshed['samples'][1]['token']
        self.assertNotEqual(new_token, token)
        self.assertEqual(store.media(new_token), Path(new_sample['video']['path']).resolve())
        self.assertEqual(store.refresh(), 0)
        self.assertFalse((self.root/'annotations').exists())

    def test_refresh_rejects_changed_or_disappeared_old_source_without_replacing_tokens(self):
        store, token = self.store()
        before = copy.deepcopy(store.manifest)
        self.sample['view'] = 'side'
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'source_row_changed'):
            store.refresh()
        self.assertEqual(store.manifest, before)
        self.assertEqual(store.media(token), Path(self.sample['video']['path']).resolve())
        self.manifest['samples'] = []
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'source_disappeared'):
            store.catalog()
        self.assertIn(token, store.tokens)

    def test_unsaved_old_form_cannot_approve_changed_source_metadata(self):
        store, token = self.store()
        payload = self.payload(store, token)
        self.sample['view'] = 'side'
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'source_row_changed'):
            store.submit(payload)
        self.assertFalse((self.root/'annotations').exists())

    def test_http_catalog_refresh_sees_new_source_and_old_video_url_stays_valid(self):
        server = self.server()
        _, _, old_body = self.request(server, 'GET', '/api/samples')
        token = json.loads(old_body)['samples'][0]['token']
        self.append_source()
        status, _, new_body = self.request(server, 'GET', '/api/samples')
        self.assertEqual(status, 200)
        result = json.loads(new_body)
        self.assertEqual(len(result['samples']), 2)
        self.assertEqual(result['samples'][0]['token'], token)
        self.assertEqual(self.request(server, 'GET', '/media/'+token, headers={'Range':'bytes=0-15'})[0], 206)

    def test_history_annotation_mutation_cannot_be_loaded(self):
        store, token = self.store()
        store.submit(self.payload(store, token))
        file = next((self.root/'annotations').rglob('*.json'))
        value = json.loads(file.read_text(encoding='utf-8'))
        value['annotation']['observable_count'] = 10
        file.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'history_source_or_annotation_changed'):
            r.load_reviewed(self.root)

    def test_accepted_operator_note_is_preserved(self):
        store, token = self.store()
        payload = self.payload(store, token)
        payload['reason'] = 'TEST: partial visibility noted without clinical judgment'
        store.submit(payload)
        self.assertEqual(r.load_reviewed(self.root)['annotations'][0]['operator_note'], payload['reason'])

    def server(self):
        server = r.make_server(self.root, 0)
        thread = Thread(target=server.serve_forever, kwargs=dict(poll_interval=.01), daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: thread.join(2))
        self.addCleanup(server.shutdown)
        return server

    def request(self, server, method, path, body=None, headers=None):
        client = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        client.request(method, path, body=body, headers=headers or {})
        result = client.getresponse()
        status, response_headers, content = result.status, dict(result.getheaders()), result.read()
        client.close()
        return status, response_headers, content

    def test_http_loopback_html_csp_blind_catalog_range_and_path_allowlist(self):
        server = self.server()
        self.assertEqual(server.server_address[0], '127.0.0.1')
        status, headers, html = self.request(server, 'GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('frame-ancestors', headers['Content-Security-Policy'])
        self.assertIn('完整观看', html.decode('utf-8'))
        _, _, body = self.request(server, 'GET', '/api/samples')
        token = json.loads(body)['samples'][0]['token']
        status, headers, content = self.request(server, 'GET', '/media/'+token, headers={'Range': 'bytes=0-15'})
        self.assertEqual(status, 206)
        self.assertEqual(len(content), 16)
        self.assertEqual(content, Path(self.sample['video']['path']).read_bytes()[:16])
        for target in ('/media/../../Windows/win.ini', '/media/'+token+'?path=C:/Windows/win.ini', '/api/file?path=x', '/manifest.json'):
            self.assertEqual(self.request(server, 'GET', target)[0], 404)
        self.assertEqual(self.request(server, 'GET', '/media/'+token, headers={'Range':'bytes=0-4,6-9'})[0], 416)

    def test_http_cross_origin_dns_rebinding_and_csrf_rejected(self):
        server = self.server()
        _, _, body = self.request(server, 'GET', '/api/samples')
        token = json.loads(body)['samples'][0]['token']
        payload = json.dumps(self.payload(server.review_store, token))
        origin = 'http://127.0.0.1:'+str(server.server_port)
        headers = {'Content-Type': 'application/json', 'Origin': origin, 'X-CSRF-Token': server.review_store.csrf}
        self.assertEqual(self.request(server, 'POST', '/api/submit', payload, headers)[0], 201)
        for bad in ({'Origin': 'http://evil.example'}, {'Origin': 'null'}, {'X-CSRF-Token': 'wrong'}, {'Host':'evil.example'}):
            failed = dict(headers); failed.update(bad)
            self.assertEqual(self.request(server, 'POST', '/api/submit', payload, failed)[0], 403)
        no_origin = dict(headers); no_origin.pop('Origin')
        self.assertEqual(self.request(server, 'POST', '/api/submit', payload, no_origin)[0], 403)
        self.assertEqual(self.request(server, 'GET', '/', headers={'Host':'evil.example'})[0], 403)

    def test_http_media_failure_does_not_disclose_blinded_filename(self):
        server = self.server()
        token = next(iter(server.review_store.tokens))
        Path(self.sample['video']['path']).unlink()
        status, _, content = self.request(server, 'GET', '/media/'+token)
        self.assertEqual(status, 400)
        self.assertNotIn(str(self.root).encode(), content)
        self.assertNotIn(b'one.mp4', content)
        self.assertNotIn(b'SECRET', content)


if __name__ == '__main__':
    unittest.main()
