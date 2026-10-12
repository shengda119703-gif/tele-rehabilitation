"""Create explicitly requested patients from a PRIVATE JSON file, without secrets in output."""
import argparse
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path


def call(base, path, payload):
    request = urllib.request.Request(base + '/api/cloud/v1' + path,
        data=json.dumps(payload).encode(), method='POST',
        headers={'Content-Type': 'application/json', 'X-Ankang-Client': 'native'})
    try:
        with urllib.request.urlopen(request, context=ssl.create_default_context(), timeout=20) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('private_file', type=Path)
    parser.add_argument('--base', default='https://139.224.216.18')
    args = parser.parse_args()
    if not args.base.startswith('https://'):
        raise SystemExit('HTTPS required')
    failed = False
    for item in json.loads(args.private_file.read_text(encoding='utf-8-sig')):
        code, session = call(args.base, '/auth/password/login', {**item, 'client_kind': 'DESKTOP'})
        created = False
        if code == 401:
            status, result = call(args.base, '/auth/register', {**item, 'display_name': item['username']})
            created = status == 201
            if not created:
                # A conflicting account is never reset or overwritten.
                print(json.dumps({'username': item['username'], 'status': status,
                                  'code': result.get('code'), 'login_verified': False}, ensure_ascii=False))
                failed = True
                continue
            code, session = call(args.base, '/auth/password/login', {**item, 'client_kind': 'DESKTOP'})
        valid = code == 200 and session.get('role') == 'PATIENT'
        if code == 200:
            # Logout the temporary provisioning session; do not leave tokens on disk.
            request = urllib.request.Request(args.base + '/api/cloud/v1/auth/logout', data=b'{}', method='POST',
                headers={'Authorization': 'Bearer ' + session['access_token'], 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=20) as response:
                response.read()
        print(json.dumps({'username': item['username'], 'created': created, 'login_verified': valid,
                          'role': session.get('role') if valid else None}, ensure_ascii=False))
        failed |= not valid
    raise SystemExit(int(failed))


if __name__ == '__main__':
    main()
