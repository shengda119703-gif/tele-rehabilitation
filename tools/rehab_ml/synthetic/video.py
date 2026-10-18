"""Real decoded PTS and shared causal frame selection for synthetic video research.

No frame time is reconstructed from nominal FPS. Pixel fingerprints describe
decoded RGB24 in original coordinates, before either pose backend preprocesses it.
"""
from __future__ import annotations

from bisect import bisect_right
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

from tools.rehab_ml.common import canonical_hash, file_hash

TIMELINE_SCHEMA = 'rehab_synthetic/v1'
FRAME_SCHEMA = 'rehab_synthetic_frames/v2'
MAX_FRAMES = 18000
MAX_SECONDS = 180.0
MAX_BYTES = 2 * 1024**3
MAX_PIXELS = 1920 * 1080


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _source(video):
    path = Path(video).resolve()
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError('bounded_existing_video_required')
    return path


def _ratio(value):
    if value is None or value.numerator <= 0 or value.denominator <= 0:
        raise ValueError('positive_real_time_base_required')
    return [int(value.numerator), int(value.denominator)]


def _new_json(path, value):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Do not replace earlier timelines, frame inventories, or human files.
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    return path


def _read(value):
    if isinstance(value, dict):
        return value
    path = Path(value).resolve()
    if not path.is_file() or not 0 < path.stat().st_size <= 32 * 1024**2:
        raise ValueError('bounded_frame_manifest_required')
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError('duplicate_json_key')
            result[key] = item
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))


def _timeline_document(timeline):
    return {key:value for key,value in timeline.items() if key not in ('timeline_path','timeline_sha256')}


def semantic_timeline_hash(timeline):
    """Bind all real media evidence, separately from the decoder version label.

    ``full_timeline_sha256`` retains its original whole-document meaning. This
    additional fingerprint remains identical across decoder versions only when
    every frame's real PTS, RGB bytes, geometry and stream origin remain equal.
    """
    document = _timeline_document(timeline)
    document['provenance'] = {key:value for key,value in document['provenance'].items()
                              if key != 'decoder_version'}
    return canonical_hash(document)


def _packet_inventory(path):
    import av
    with av.open(str(path)) as container:
        if len(container.streams.video) != 1:
            raise ValueError('exactly_one_video_stream_required')
        stream = container.streams.video[0]
        if stream.start_time is None:
            raise ValueError('explicit_stream_start_time_required')
        ratio = _ratio(stream.time_base)
        origin = Fraction(stream.start_time) * stream.time_base
        packets, discarded = [], 0
        for packet in container.demux(stream):
            if not packet.size:
                continue
            if packet.is_corrupt or packet.pts is None:
                raise ValueError('corrupt_packet_or_missing_real_pts')
            _ratio(packet.time_base)
            if packet.is_discard:
                discarded += 1
            else:
                packets.append(Fraction(packet.pts) * packet.time_base - origin)
            if len(packets) + discarded > MAX_FRAMES:
                raise ValueError('video_packet_budget_exceeded')
        packets.sort()
        if (not packets or any(b <= a for a, b in zip(packets, packets[1:]))
                or packets[0] < 0 or packets[-1] > MAX_SECONDS):
            raise ValueError('strict_nonnegative_presentation_timeline_required')
        if stream.frames and int(stream.frames) != len(packets) + discarded:
            raise ValueError('packet_inventory_disagrees_with_advertised_frames')
        return dict(stream_index=stream.index, origin=origin,
                    start_pts=int(stream.start_time), time_base=ratio,
                    presentation=packets, discarded=discarded)


def probe_video(video, *, timeline_path=None):
    """Fully decode and verify a single video; optionally create a new timeline.

    The returned timeline includes all real presentation times and integer PTS,
    not just selected inference frames. This does not approve motion or labels.
    """
    import av
    path = _source(video)
    fingerprint = file_hash(path)
    inventory = _packet_inventory(path)
    records, size = [], None
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        for index, frame in enumerate(container.decode(stream)):
            if index >= MAX_FRAMES or frame.is_corrupt or frame.pts is None:
                raise ValueError('corrupt_missing_pts_or_decode_budget_exceeded')
            ratio = _ratio(frame.time_base)
            stamp = Fraction(frame.pts) * frame.time_base - inventory['origin']
            if index >= len(inventory['presentation']) or stamp != inventory['presentation'][index]:
                raise ValueError('decoded_frame_disagrees_with_packet_pts')
            image = frame.to_ndarray(format='rgb24')
            height, width = image.shape[:2]
            if (min(width, height) < 32 or width * height > MAX_PIXELS
                    or size is not None and size != [width, height]):
                raise ValueError('constant_original_video_pixel_budget_required')
            size = [width, height]
            records.append(dict(frame_index=index, pts=int(frame.pts), time_base=ratio,
                                timestamp_s=float(stamp), source_size=size,
                                decoded_rgb_sha256=hashlib.sha256(image.tobytes()).hexdigest()))
    if len(records) != len(inventory['presentation']):
        raise ValueError('decoder_ended_before_full_packet_timeline')
    if file_hash(path) != fingerprint:
        raise ValueError('source_changed_while_decoding')
    result = dict(schema_version=TIMELINE_SCHEMA, video_sha256=fingerprint,
                  frame_count=len(records), width=size[0], height=size[1],
                  time_basis='stream_relative_media_pts',
                  presentation_s=[row['timestamp_s'] for row in records],
                  frames=records,
                  provenance=dict(decoder='pyav', decoder_version=av.__version__,
                                  origin='decoded_video', video_stream_index=inventory['stream_index'],
                                  stream_start_time_s=float(inventory['origin']),
                                  stream_start_pts=inventory['start_pts'],
                                  stream_time_base=inventory['time_base'],
                                  discarded_packets=inventory['discarded'],
                                  pixel_format='rgb24', full_decode_verified=True))
    if timeline_path is not None:
        target = _new_json(timeline_path, result)
        # Path/hash are returned separately; they are not part of their own hash.
        return {**result, 'timeline_path': str(target), 'timeline_sha256': file_hash(target)}
    return result


def create_frame_manifest(video, output_path=None, *, sampling_hz=15.0, probe=None):
    """Select latest already-arrived frames on a fixed grid; never interpolate.

    Duplicated frame indices on a slow source are omitted, retaining actual gaps.
    sample_age_s makes the age at the grid tick explicit for VFR recordings.
    """
    path = _source(video)
    if not _finite(sampling_hz) or not 0 < sampling_hz <= 60:
        raise ValueError('bounded_positive_sampling_hz_required')
    timeline = probe_video(path) if probe is None else probe
    if (timeline.get('schema_version') != TIMELINE_SCHEMA
            or timeline.get('video_sha256') != file_hash(path)
            or timeline.get('frame_count') != len(timeline.get('frames', []))):
        raise ValueError('matching_full_decoded_probe_required')
    stamps = timeline['presentation_s']
    if (not stamps or len(stamps) != timeline['frame_count']
            or any(not _finite(t) or t < 0 for t in stamps)
            or any(b <= a for a, b in zip(stamps, stamps[1:]))):
        raise ValueError('strict_full_pts_timeline_required')
    selected, previous = [], None
    ticks = math.floor((stamps[-1] - stamps[0]) * sampling_hz + 1e-9) + 1
    for tick in range(ticks):
        target = stamps[0] + tick / sampling_hz
        index = bisect_right(stamps, target + 1e-10) - 1
        if index == previous:
            continue
        row = dict(timeline['frames'][index])
        row.update(sample_grid_time_s=target, sample_age_s=max(0., target - row['timestamp_s']))
        selected.append(row)
        previous = index
    result = dict(schema_version=FRAME_SCHEMA, source_path=str(path),
                  source_sha256=timeline['video_sha256'],
                  source_size=[timeline['width'], timeline['height']],
                  all_frame_count=timeline['frame_count'], sampling_hz=float(sampling_hz),
                  time_basis='stream_relative_media_pts',
                  stream_start_pts=timeline['provenance']['stream_start_pts'],
                  stream_time_base=timeline['provenance']['stream_time_base'],
                  selection='latest_frame_at_or_before_grid_tick_unique_indices',
                  interpolation=False, nominal_fps_used=False,
                  full_timeline_sha256=canonical_hash(_timeline_document(timeline)),
                  semantic_timeline_sha256=semantic_timeline_hash(timeline),
                  semantic_timeline_hash_scope='all_real_pts_rgb24_geometry_stream_origin_without_decoder_version',
                  timeline_provenance=dict(timeline['provenance']),
                  frames=selected)
    validate_frame_manifest(result, video=path)
    if output_path is not None:
        _new_json(output_path, result)
    return result


def validate_frame_manifest(value, *, video=None, verify_decode=False):
    manifest = _read(value)
    if (manifest.get('schema_version') != FRAME_SCHEMA or manifest.get('time_basis') != 'stream_relative_media_pts'
            or manifest.get('interpolation') is not False or manifest.get('nominal_fps_used') is not False
            or manifest.get('selection') != 'latest_frame_at_or_before_grid_tick_unique_indices'
            or manifest.get('semantic_timeline_hash_scope') != 'all_real_pts_rgb24_geometry_stream_origin_without_decoder_version'
            or not isinstance(manifest.get('timeline_provenance'),dict)
            or manifest['timeline_provenance'].get('decoder') != 'pyav'
            or not isinstance(manifest['timeline_provenance'].get('decoder_version'),str)):
        raise ValueError('unsupported_shared_frame_manifest')
    for key in ('full_timeline_sha256','semantic_timeline_sha256'):
        sha = manifest.get(key)
        if not isinstance(sha,str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('full_document_and_media_semantic_timeline_fingerprints_required')
    source = _source(video if video is not None else manifest['source_path'])
    if manifest.get('source_sha256') != file_hash(source):
        raise ValueError('frame_manifest_source_sha256_mismatch')
    size = manifest.get('source_size')
    if (not isinstance(size, list) or len(size) != 2
            or any(type(n) is not int or n < 32 for n in size) or math.prod(size) > MAX_PIXELS):
        raise ValueError('frame_manifest_source_size_invalid')
    count, rows = manifest.get('all_frame_count'), manifest.get('frames')
    if type(count) is not int or not 1 <= count <= MAX_FRAMES or not isinstance(rows, list) or not rows:
        raise ValueError('nonempty_bounded_frame_inventory_required')
    previous_index, previous_stamp = -1, -math.inf
    origin = Fraction(manifest['stream_start_pts']) * Fraction(*manifest['stream_time_base'])
    for row in rows:
        index, stamp = row.get('frame_index'), row.get('timestamp_s')
        ratio, pts = row.get('time_base'), row.get('pts')
        if (type(index) is not int or not previous_index < index < count
                or type(pts) is not int or not isinstance(ratio, list) or len(ratio) != 2
                or any(type(n) is not int or n <= 0 for n in ratio)
                or not _finite(stamp) or not previous_stamp < stamp <= MAX_SECONDS or stamp < 0
                or abs(float(Fraction(pts) * Fraction(*ratio) - origin) - stamp) > 1e-10
                or row.get('source_size') != size):
            raise ValueError('invalid_or_nonmatching_real_frame_pts')
        sha = row.get('decoded_rgb_sha256')
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('decoded_rgb_fingerprint_required')
        grid, age = row.get('sample_grid_time_s'), row.get('sample_age_s')
        if (not _finite(grid) or not _finite(age) or age < 0 or grid + 1e-10 < stamp
                or abs(max(0., grid - stamp) - age) > 1e-10):
            raise ValueError('causal_sample_age_required')
        previous_index, previous_stamp = index, stamp
    if verify_decode:
        decoded = probe_video(source)
        actual = create_frame_manifest(source, sampling_hz=manifest['sampling_hz'], probe=decoded)
        original_provenance = manifest['timeline_provenance']
        if ({k:v for k,v in original_provenance.items() if k != 'decoder_version'} !=
                {k:v for k,v in decoded['provenance'].items() if k != 'decoder_version'}):
            raise ValueError('timeline_provenance_media_facts_disagree_with_actual_decode')
        # Reconstruct the original full document from fully decoded current media
        # plus the separately preserved producer's decoder version. No PTS,
        # source SHA, pixel hash or stream-origin field is omitted from this check.
        original_document = dict(decoded, provenance=original_provenance)
        if canonical_hash(original_document) != manifest['full_timeline_sha256']:
            raise ValueError('full_timeline_document_fingerprint_disagrees_with_actual_decode')
        actual['full_timeline_sha256'] = manifest['full_timeline_sha256']
        actual['timeline_provenance'] = original_provenance
        if canonical_hash(actual) != canonical_hash({**manifest, 'source_path': str(source)}):
            raise ValueError('frame_manifest_disagrees_with_actual_decode')
    return manifest


def iter_selected_rgb(video, manifest):
    """Decode again and verify each selected frame, yielding original RGB24."""
    import av
    path = _source(video)
    manifest = validate_frame_manifest(manifest, video=path)
    wanted = {row['frame_index']: row for row in manifest['frames']}
    seen, count = 0, 0
    with av.open(str(path)) as container:
        if len(container.streams.video) != 1:
            raise ValueError('exactly_one_video_stream_required')
        stream = container.streams.video[0]
        for index, frame in enumerate(container.decode(stream)):
            count += 1
            if index not in wanted:
                continue
            row = wanted[index]
            image = frame.to_ndarray(format='rgb24')
            if (frame.is_corrupt or frame.pts != row['pts'] or _ratio(frame.time_base) != row['time_base']
                    or list(image.shape[1::-1]) != manifest['source_size']
                    or hashlib.sha256(image.tobytes()).hexdigest() != row['decoded_rgb_sha256']):
                raise ValueError('selected_frame_pts_size_or_pixel_fingerprint_mismatch')
            seen += 1
            yield row, image
    if seen != len(wanted) or count != manifest['all_frame_count'] or file_hash(path) != manifest['source_sha256']:
        raise ValueError('selected_frame_inventory_or_source_changed')
