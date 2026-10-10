from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import time
import zipfile

import requests

from .common import file_hash, load_registry, paths, read_json, utc_now, write_json

TIMEOUT = (10, 40)


def checked_zip(path, *, max_bytes=2_000_000_000, max_files=50_000):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > max_files or sum(e.file_size for e in entries) > max_bytes:
            raise ValueError('Archive extraction quota exceeded')
        names = set()
        for entry in entries:
            name = entry.filename.replace('\\', '/')
            item = PurePosixPath(name)
            canonical = str(item).casefold()
            reserved = any(part != part.rstrip(' .') or re.fullmatch(
                r'(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part, re.I) for part in item.parts)
            if (name.startswith('/') or '..' in item.parts or re.match(r'^[A-Za-z]:', name)
                    or '\x00' in name or ':' in name or canonical in names or reserved
                    or canonical == '.' or len(item.parts) > 32
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError('Unsafe or duplicate archive member: ' + name)
            names.add(canonical)
            if entry.file_size > 100_000_000 or (entry.file_size > 10_000_000
                                                 and entry.file_size / max(1, entry.compress_size) > 300):
                raise ValueError('Suspicious archive member size or ratio')
        return entries


def resolve(registry=None):
    resolved = {}
    for key, record in load_registry(registry).items():
        result = dict(record, resolved_at=utc_now())
        if not record.get('api'):
            resolved[key] = result
            continue
        try:
            response = requests.get(record['api'], timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
            if key == 'intellirehabds':
                if str(data['id']) != str(record['record_id']) or data['metadata']['version'] != record['version']:
                    raise ValueError('Pinned dataset record/version mismatch')
                files = {item['key']: item for item in data['files']}
                for item in record['files']:
                    actual = files[item['name']]
                    if actual['size'] != item['bytes'] or actual['checksum'] != 'md5:' + item['md5']:
                        raise ValueError('Pinned file size/checksum changed; quarantine, do not silently update')
                result['resolved_status'] = 'ready'
                result['record_metadata'] = data
            else:
                versions = data.get('data', {}).get('latestVersion', {})
                result['published_metadata'] = versions
                result['resolved_status'] = 'blocked_license_review'
                if versions.get('versionState') != 'RELEASED':
                    result['resolved_status'] = 'blocked_no_verified_released_version'
        except (requests.RequestException, ValueError, KeyError) as exc:
            result['resolved_status'] = 'blocked_metadata'
            result['error'] = str(exc)
        resolved[key] = result
    output = paths()['data'] / 'registry-resolved.json'
    write_json(output, resolved)
    if resolved['intellirehabds'].get('resolved_status') != 'ready':
        raise RuntimeError('IRDS official metadata not verified: ' + str(output))
    return dict(path=str(output), status={key: value.get('resolved_status', value['license_status'])
                                        for key, value in resolved.items()})


def download_file(spec, destination, *, session=None, retries=4):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = spec['bytes']
    def verified(path):
        return path.stat().st_size == expected and file_hash(path, 'md5') == spec['md5']
    if destination.exists():
        if verified(destination):
            return dict(path=str(destination), bytes=expected, sha256=file_hash(destination), cached=True)
        quarantine = destination.with_name(destination.name + '.quarantine-' + str(time.time_ns()))
        os.replace(destination, quarantine)
        raise ValueError('Existing file checksum mismatch; preserved as ' + str(quarantine))
    partial = destination.with_name(destination.name + '.part')
    available = shutil.disk_usage(destination.parent).free
    remaining = expected - (partial.stat().st_size if partial.exists() else 0)
    if available < max(0, remaining) + 256_000_000:
        raise OSError('Insufficient space; require remaining download plus 256 MB reserve')
    session = session or requests.Session()
    for attempt in range(retries):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset == expected:
            break
        if offset > expected:
            os.replace(partial, partial.with_name(partial.name + '.quarantine-' + str(time.time_ns())))
            raise ValueError('Partial file exceeds pinned size')
        try:
            with session.get(spec['url'], headers={'Range': f'bytes={offset}-'} if offset else {},
                             timeout=TIMEOUT, stream=True) as response:
                response.raise_for_status()
                mode = 'ab' if offset and response.status_code == 206 else 'wb'
                if response.status_code not in (200, 206):
                    raise ValueError('Unsupported HTTP status')
                if response.status_code == 206:
                    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                    if not match or int(match[1]) != offset or int(match[3]) != expected:
                        raise ValueError('Invalid resume Content-Range')
                # Servers ignoring Range return 200: restart, never append a full file.
                written = offset if mode == 'ab' else 0
                with partial.open(mode) as stream:
                    for block in response.iter_content(1024 * 1024):
                        if not block:
                            continue
                        written += len(block)
                        if written > expected:
                            raise ValueError('Download exceeded pinned size')
                        stream.write(block)
                    stream.flush()
                    os.fsync(stream.fileno())
            if partial.stat().st_size == expected:
                break
            raise requests.ConnectionError('Truncated download')
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(min(2 ** attempt, 5))
    if not partial.exists() or not verified(partial):
        if partial.exists() and partial.stat().st_size == expected:
            quarantine = partial.with_name(partial.name + '.quarantine-' + str(time.time_ns()))
            os.replace(partial, quarantine)
        raise ValueError('Incomplete download or checksum mismatch; final file not published')
    if destination.suffix == '.zip':
        checked_zip(partial)
    os.replace(partial, destination)
    return dict(path=str(destination), bytes=expected, sha256=file_hash(destination), cached=False)


def fetch(dataset):
    registry = load_registry()
    record = registry[dataset]
    if record['license_status'] != 'verified_dataset_license':
        raise PermissionError('Dataset not authorized: ' + record['license_status'])
    metadata_path = paths()['data'] / 'registry-resolved.json'
    if not metadata_path.exists():
        resolve()
    metadata = read_json(metadata_path)[dataset]
    if metadata.get('resolved_status') != 'ready':
        raise ValueError('Official metadata not verified')
    raw = paths()['data'] / dataset / record['version'] / 'raw'
    files = []
    for spec in record['files']:
        files.append(dict(name=spec['name'], md5=spec['md5'], **download_file(spec, raw / spec['name'])))
    manifest = dict(dataset=dataset, version=record['version'], record_id=record['record_id'],
                    license=record['license'], license_evidence=record['license_evidence'],
                    attribution=record['attribution'], files=files, downloaded_at=utc_now())
    output = raw.parent / 'download-manifest.json'
    write_json(output, manifest)
    return dict(manifest=str(output), files=files)


def verify(dataset):
    record = load_registry()[dataset]
    raw = paths()['data'] / dataset / record['version'] / 'raw'
    files = []
    for spec in record['files']:
        path = raw / spec['name']
        if path.stat().st_size != spec['bytes'] or file_hash(path, 'md5') != spec['md5']:
            raise ValueError('File verification failed: ' + str(path))
        if path.suffix == '.zip':
            entries = checked_zip(path)
            with zipfile.ZipFile(path) as archive:
                bad = archive.testzip()
            if bad:
                raise ValueError('ZIP CRC failed: ' + bad)
        else:
            entries = []
        files.append(dict(name=spec['name'], sha256=file_hash(path), entries=len(entries)))
    return dict(dataset=dataset, verified=True, files=files)
