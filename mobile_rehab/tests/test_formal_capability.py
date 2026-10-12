"""Real optional HTTP capability; no camera, body or qualified-plan fixtures."""
from fastapi.testclient import TestClient
from mobile_rehab.server import create_app


def test_disabled_formal_has_no_grant_or_endpoint(tmp_path):
    with TestClient(create_app(tmp_path, pair_key='TEST-capability')) as client:
        client.post('/api/pair', json={'code': 'TEST-capability'}, headers={'X-Rehab-Client': 'mobile-v1'})
        assert client.get('/api/catalog').json()['formal_measurement'] is None
        assert client.get('/api/rehab/v2/sessions').status_code == 404


def test_enabled_formal_declares_actual_source_without_eligibility(tmp_path):
    with TestClient(create_app(tmp_path, pair_key='TEST-capability', rehab_v2=True)) as client:
        assert client.get('/api/catalog').status_code == 401
        client.post('/api/pair', json={'code': 'TEST-capability'}, headers={'X-Rehab-Client': 'mobile-v1'})
        capability = client.get('/api/catalog').json()['formal_measurement']
        assert capability['provider'] == 'hosted-rehab-v2-1'
        assert capability['owner_scope'] == client.cookies['rehab_device'].split('.')[0]
        assert capability['source_context'] == 'LIVE_CAMERA:SELF_USE'
        assert capability['protocols'] == [dict(exercise_id='shoulder_abduction', view='frontal'),
                                          dict(exercise_id='sit_to_stand', view='sagittal'),
                                          dict(exercise_id='rehab_squat', view='sagittal')]
        assert 'execution_allowed' not in capability
        assert client.get('/api/rehab/v2/sessions').json()['items'] == []
