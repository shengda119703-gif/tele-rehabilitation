"""Read-only official published metadata; never accepts terms or authorizes training."""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import requests

from .common import ROOT, canonical_hash, file_hash, load_registry, paths, utc_now, write_json

BASE = 'https://dataverse.harvard.edu/api/v1'
PIDS = {'mobiphysio': 'doi:10.7910/DVN/XSI0QN',
        'sumedipose': 'doi:10.7910/DVN/GRRROM'}
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
TIMEOUT = (10, 20)


def _envelope(value):
    if not isinstance(value, dict) or value.get('status') != 'OK' or not isinstance(value.get('data'), dict):
        raise ValueError('Official metadata is not an OK dataset object')
    return value['data']


def _positive_int(value, name, *, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError('Invalid official ' + name)
    return value


def _version(value, pid):
    if value.get('versionState') != 'RELEASED':
        raise ValueError('Dataset version is not RELEASED; draft/deaccessioned data refused')
    if value.get('datasetPersistentId', '').casefold() != pid.casefold():
        raise ValueError('Published dataset persistent ID mismatch')
    major = _positive_int(value.get('versionNumber'), 'major version')
    minor = _positive_int(value.get('versionMinorNumber'), 'minor version', minimum=0)
    return f'{major}.{minor}'


def _view(value, pid):
    version = _version(value, pid)
    records = value.get('files')
    if not isinstance(records, list) or not records:
        raise ValueError('Published file inventory is missing or empty')
    files, ids = [], set()
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get('dataFile'), dict):
            raise ValueError('Malformed official file metadata')
        item = row['dataFile']
        file_id = _positive_int(item.get('id'), 'file ID')
        if file_id in ids:
            raise ValueError('Duplicate official file ID')
        ids.add(file_id)
        name = item.get('filename')
        if not isinstance(name, str) or not name or '\x00' in name:
            raise ValueError('Missing official filename')
        size = _positive_int(item.get('filesize'), 'file size', minimum=0)
        checksum = item.get('checksum') or {}
        algorithm = str(checksum.get('type', '')).lower().replace('-', '')
        checksum_value = str(checksum.get('value', '')).lower()
        length = {'md5': 32, 'sha1': 40, 'sha256': 64}.get(algorithm)
        if length is None or not re.fullmatch('[0-9a-f]{'+str(length)+'}', checksum_value):
            raise ValueError('Unverified official file checksum')
        restricted = row.get('restricted')
        embargo = row.get('embargo') or item.get('embargo')
        # False must be explicit. fileAccessRequest means requests are supported,
        # not that an unrestricted file requires an access request.
        access = ('unknown' if type(restricted) is not bool else
                  'restricted' if restricted else 'embargoed' if embargo else 'unrestricted_metadata')
        files.append(dict(file_id=file_id, filename=name, label=row.get('label'),
                          directory_label=item.get('directoryLabel'), bytes=size,
                          checksum=dict(algorithm=algorithm, value=checksum_value),
                          restricted=restricted, embargo=embargo, access_status=access,
                          access_request_supported=item.get('fileAccessRequest'),
                          tabular_data=item.get('tabularData'),
                          original_filename=item.get('originalFileName'),
                          original_bytes=item.get('originalFileSize'),
                          access_url=f'{BASE}/access/datafile/{file_id}'))
    terms = {key: value.get(key) for key in ('termsOfUse', 'termsOfAccess', 'restrictions',
             'conditions', 'disclaimer', 'confidentialityDeclaration', 'specialPermissions',
             'depositorRequirements', 'accessConditions', 'dataAccessPlace',
             'originalArchive', 'availabilityStatus', 'citationRequirements')}
    return dict(dataset_id=_positive_int(value.get('datasetId'), 'dataset ID'),
                persistent_id=pid, version=version, version_id=_positive_int(value.get('id'), 'version ID'),
                state='RELEASED', release_time=value.get('releaseTime'),
                license=value.get('license'), terms=terms,
                files=sorted(files, key=lambda row: row['file_id']))


def inspect_published(dataset, get_json):
    """A getter permits TEST metadata contracts without any live file downloads."""
    pid = PIDS[dataset]
    query = urlencode({'persistentId': pid})
    root_url = f'{BASE}/datasets/:persistentId/?{query}'
    root = _envelope(get_json(root_url))
    dataset_id = _positive_int(root.get('id'), 'dataset ID')
    latest_url = f'{BASE}/datasets/:persistentId/versions/:latest-published?{query}'
    latest = _view(_envelope(get_json(latest_url)), pid)
    pinned_url = f'{BASE}/datasets/:persistentId/versions/{latest["version"]}?{query}'
    pinned = _view(_envelope(get_json(pinned_url)), pid)
    if latest['dataset_id'] != dataset_id or pinned != latest:
        raise ValueError('Published version identity, terms or file inventory changed while pinning')
    guestbook_id = root.get('guestbookId')
    license_info = pinned['license'] if isinstance(pinned['license'], dict) else {}
    license_name = license_info.get('name')
    license_uri = license_info.get('uri')
    restricted_use = (isinstance(license_uri, str) and
                      re.fullmatch(r'https?://creativecommons\.org/licenses/by-nc-sa/4\.0/?', license_uri))
    cc0 = (isinstance(license_uri, str) and
           re.fullmatch(r'https?://creativecommons\.org/publicdomain/zero/1\.0/?', license_uri))
    return dict(schema_version='dataverse-published-metadata-1', dataset=dataset,
                resolved_status='blocked_requires_eligibility_confirmation' if restricted_use else
                    'blocked_access_and_task_review' if cc0 else 'blocked_license_and_task_review',
                metadata_status='published_version_pinned', published=pinned,
                published_inventory_sha256=canonical_hash(pinned),
                pinned_metadata_url=pinned_url, license_name=license_name, license_uri=license_uri,
                guestbook_id=guestbook_id,
                guestbook_status='configured' if guestbook_id else 'not_configured' if guestbook_id == 0 else 'not_reported',
                file_count=len(pinned['files']), total_file_bytes=sum(f['bytes'] for f in pinned['files']),
                file_access_counts={key: sum(f['access_status'] == key for f in pinned['files'])
                                    for key in ('unrestricted_metadata', 'restricted', 'embargoed', 'unknown')},
                license_status='verified_nc_sa_metadata_requires_eligibility' if restricted_use else
                    'verified_cc0_metadata_pending_access_and_task_review' if cc0 else 'pending_application_license_and_task_review',
                downloaded_data_bytes=0, download_authorized=False, training_authorized=False,
                product_enabled=False,
                limitations=['Metadata availability does not prove file download access or usage eligibility.',
                             'Tabular original-format bytes/checksums may differ from stored/archival metadata.',
                             'No account, guestbook response, terms acceptance or access request is submitted.',
                             'RGB, keypoint mapping and independent supervision have not been validated.'])


def audit_dataverse(dataset, record=None):
    if dataset not in PIDS:
        raise ValueError('Only the two explicitly registered official datasets may be inspected')
    record = load_registry()[dataset] if record is None else record
    if record.get('persistent_id', PIDS[dataset]) != PIDS[dataset]:
        raise ValueError('Registry persistent ID differs from fixed official dataset')
    root = paths()['run'] / ('dataverse-'+dataset+'-'+uuid4().hex[:8])
    root.mkdir()
    requests_log = []

    def get_json(url):
        started = time.monotonic()
        log = dict(url=url, timeout_connect_s=TIMEOUT[0], timeout_read_s=TIMEOUT[1],
                   max_response_bytes=MAX_RESPONSE_BYTES, credentials_sent=False)
        requests_log.append(log)
        try:
            with requests.get(url, timeout=TIMEOUT, stream=True, allow_redirects=False) as response:
                log['http_status'] = response.status_code
                if response.status_code != 200:
                    raise requests.HTTPError('Official metadata HTTP '+str(response.status_code))
                if 'json' not in response.headers.get('Content-Type', '').lower():
                    raise ValueError('Non-JSON response; challenge or login page is not dataset metadata')
                body = bytearray()
                for block in response.iter_content(65536):
                    body.extend(block)
                    if len(body) > MAX_RESPONSE_BYTES or time.monotonic()-started > 45:
                        raise ValueError('Metadata size or elapsed-time budget exceeded')
                import json
                value = json.loads(body)
            path = root / f'response-{len(requests_log):02}.json'
            write_json(path, value)
            log.update(bytes=len(body), snapshot=str(path), snapshot_sha256=file_hash(path),
                       payload_sha256=canonical_hash(value), status='received')
            return value
        except Exception as exc:
            log.update(status='failed', error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            log['elapsed_s'] = time.monotonic()-started
            write_json(root / 'requests.json', requests_log)

    try:
        result = inspect_published(dataset, get_json)
    except Exception as exc:
        result = dict(schema_version='dataverse-published-metadata-1', dataset=dataset,
                      metadata_status='unverified', resolved_status='blocked_metadata',
                      error_type=type(exc).__name__, error=str(exc),
                      downloaded_data_bytes=0, download_authorized=False,
                      training_authorized=False, product_enabled=False)
    result.update(run_id=root.name, resolved_at=utc_now(),
                  source_sha256={str(path): file_hash(path) for path in
                      (__file__, ROOT / 'configs/rehab_ml/datasets.yaml')},
                  requests=requests_log)
    write_json(root / 'summary.json', result)
    return result


def metadata_file_specs(audit, file_ids):
    """Allow only small CC0 documentation/score files; no implicit video or training."""
    if (audit.get('dataset') != 'mobiphysio' or audit.get('metadata_status') != 'published_version_pinned'
            or audit.get('published_inventory_sha256') != canonical_hash(audit.get('published'))):
        raise ValueError('An intact explicitly pinned MobiPhysio audit is required')
    published = audit['published']
    if published.get('persistent_id') != PIDS['mobiphysio']:
        raise ValueError('Pinned inventory is not the registered MobiPhysio DOI')
    license_info = published.get('license') or {}
    if not re.fullmatch(r'https?://creativecommons\.org/publicdomain/zero/1\.0/?', str(license_info.get('uri'))):
        raise PermissionError('This bounded documentation fetch requires official CC0 metadata')
    if any(value not in (None, '') for value in published.get('terms', {}).values()):
        raise PermissionError('Additional official terms require review before downloading')
    if audit.get('guestbook_id'):
        raise PermissionError('No guestbook response may be submitted automatically')
    if not 1 <= len(file_ids) <= 2 or len(set(file_ids)) != len(file_ids):
        raise ValueError('Select one or two distinct actual documentation file IDs')
    files = {row['file_id']: row for row in published['files']}
    specs = []
    for file_id in file_ids:
        _positive_int(file_id, 'requested file ID')
        if file_id not in files:
            raise ValueError('File ID is not in the pinned published inventory')
        row = files[file_id]
        name = row['filename']
        if (row['access_status'] != 'unrestricted_metadata' or row.get('restricted') is not False
                or row.get('embargo') or row.get('tabular_data') is not False):
            raise PermissionError('Restricted, embargoed or converted tabular files are not enabled')
        if (row['bytes'] > 2*1024*1024 or Path(name).suffix.lower() not in ('.md', '.txt', '.csv', '.json')
                or any(char in name for char in '\\/:\x00') or name != name.rstrip(' .')
                or re.fullmatch(r'(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', name, re.I)):
            raise ValueError('Only small safe documentation or score-table files may be downloaded')
        if row['checksum']['algorithm'] != 'md5':
            raise ValueError('Current downloader requires the actual official MD5')
        specs.append(dict(file_id=file_id, name=name, bytes=row['bytes'],
                          md5=row['checksum']['value'], url=f'{BASE}/access/datafile/{file_id}'))
    return specs


def load_verified_audit(audit_run):
    from .common import read_json
    audit_run = Path(audit_run).resolve()
    if (not audit_run.is_relative_to(paths()['run']) or
            not re.fullmatch(r'dataverse-mobiphysio-[0-9a-f]{8}', audit_run.name)):
        raise ValueError('Select an explicit owned MobiPhysio audit run under the research run root')
    audit = read_json(audit_run / 'summary.json')
    # Re-read the immutable numeric-version snapshot, not just its summary.
    pinned_requests = [row for row in audit['requests'] if '/versions/'+audit['published']['version']+'?' in row['url']]
    if len(pinned_requests) != 1:
        raise ValueError('Exactly one pinned numeric-version snapshot is required')
    source = pinned_requests[0]
    snapshot = Path(source['snapshot']).resolve()
    if not snapshot.is_relative_to(audit_run) or file_hash(snapshot) != source['snapshot_sha256']:
        raise ValueError('Official pinned metadata snapshot is missing or changed')
    if _view(_envelope(read_json(snapshot)), PIDS['mobiphysio']) != audit['published']:
        raise ValueError('Summary differs from the retained official numeric-version response')
    return audit_run, audit


def fetch_metadata(audit_run, file_ids):
    from .download import download_file
    audit_run, audit = load_verified_audit(audit_run)
    specs = metadata_file_specs(audit, file_ids)
    root = paths()['data'] / 'mobiphysio' / audit['published']['version'] / ('metadata-'+uuid4().hex[:8])
    root.mkdir(parents=True)
    result = dict(schema_version='dataverse-documentation-fetch-1', dataset='mobiphysio',
                  version=audit['published']['version'], status='running',
                  audit_run=audit_run.name, audit_summary_sha256=file_hash(audit_run / 'summary.json'),
                  official_inventory_sha256=audit['published_inventory_sha256'],
                  license=audit['published']['license'], files=[], training_authorized=False,
                  rgb_video_downloaded=False, model_activated=False)
    try:
        for spec in specs:
            row = download_file(spec, root / spec['name'])
            result['files'].append(dict(file_id=spec['file_id'], filename=spec['name'],
                                        md5=spec['md5'], **row))
        result['status'] = 'verified_documentation_download'
    except Exception as exc:
        result.update(status='blocked_file_download', error_type=type(exc).__name__, error=str(exc))
    result.update(downloaded_bytes=sum(row['bytes'] for row in result['files']),
                  manifest=str(root / 'manifest.json'), completed_at=utc_now())
    write_json(root / 'manifest.json', result)
    return result
