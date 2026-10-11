"""Existing lifecycle tests await the new v2 durable commit, not a 202 body."""
import time


def finish_http(client, endpoint, payload):
    response = client.post(endpoint+'/finish', json=payload)
    if response.status_code not in (200, 202):
        raise AssertionError(response.text)
    if response.status_code == 200:
        if response.json().get('status') != 'finalized':
            raise AssertionError(response.text)
        return response.json()
    accepted = response.json()
    if accepted.get('status') != 'finishing' or accepted.get('session_id') != endpoint.rsplit('/', 1)[1]:
        raise AssertionError(response.text)
    deadline = time.monotonic()+5.
    while time.monotonic() < deadline:
        result = client.get(endpoint+'/commit')
        if result.status_code != 200:
            raise AssertionError(result.text)
        receipt = result.json().get('receipt')
        if receipt:
            if receipt['status'] != 'finalized' or receipt['session_id'] != accepted['session_id']:
                raise AssertionError(result.text)
            return receipt
        time.sleep(.01)
    raise AssertionError('accepted_finish_did_not_commit: '+result.text)
