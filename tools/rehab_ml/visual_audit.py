from __future__ import annotations

import sys
import os
from pathlib import Path

import numpy as np

from .common import ROOT, file_hash, write_json
from .data import JOINTS, load_prepared


def render(output_dir=None):
    # Only a publicly licensed sample; no private target RGB or product screenshots.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    skill = Path(os.environ.get('REHAB_VISUAL_SKILL_ROOT', 'C:/Users/Administrator/.codex/skills/scientific-visualization'))
    if not (skill / 'scripts/figure_export.py').is_file():
        raise RuntimeError('Install scientific-visualization or set REHAB_VISUAL_SKILL_ROOT for offline figure helpers')
    sys.path.insert(0, str(skill / 'scripts'))
    from style_presets import style_context
    from figure_export import export_figure
    directory, manifest = load_prepared()
    samples = sorted((s for s in manifest['samples'] if s['quality_label_mask']), key=lambda s: s['sample_id'])
    sample = samples[0]  # Selection declared before looking at coordinates; no cherry picking.
    with np.load(directory / sample['npz'], allow_pickle=False) as raw:
        index = len(raw['time_s']) // 2
        xy, state = raw['coordinates'][index], raw['tracking_state'][index]
    from .common import paths
    destination = Path(output_dir).resolve() if output_dir else ROOT / 'reports/rehab_backend/figures'
    if not (destination.is_relative_to(ROOT / 'reports/rehab_backend') or destination.is_relative_to(paths()['run'])):
        raise ValueError('Figure output must stay within backend reports or the dedicated run root')
    if any((destination / name).exists() for name in ('kinect_mapping.png', 'kinect_mapping.svg',
            'kinect_mapping.export.json', 'kinect_mapping_source.json')):
        raise FileExistsError('Audit artifacts already exist; use --output-dir with a new run directory')
    destination.mkdir(parents=True, exist_ok=True)
    source = dict(sample_id=sample['sample_id'], frame_index=index, schema_id=sample['schema_id'],
        source_member=sample['source_member'], npz_sha256=sample['npz_sha256'],
        coordinate_unit='metre', coordinate_space='kinect_camera_3d', side=sample['side'],
        time_basis='nominal_30fps_not_exposure_clock', license=manifest['license'], attribution=manifest['attribution'],
        joints=[dict(index=i, name=name, xyz=point.tolist(), tracking_state=int(s))
                for i, (name, point, s) in enumerate(zip(JOINTS, xy, state))])
    data_path = destination / 'kinect_mapping_source.json'
    write_json(data_path, source)
    edges = [(0, 1), (1, 20), (20, 2), (2, 3), (20, 4), (4, 5), (5, 6), (6, 7),
             (20, 8), (8, 9), (9, 10), (10, 11), (0, 12), (12, 13), (13, 14), (14, 15),
             (0, 16), (16, 17), (17, 18), (18, 19), (7, 21), (7, 22), (11, 23), (11, 24)]
    with style_context('default', palette_name='okabe_ito_on_white'):
        fig, axes = plt.subplots(1, 2, figsize=(12, 7.2), layout='constrained')
        for ax, horizontal, title in zip(axes, (0, 2), ('A  Camera X-Y projection', 'B  Camera Z-Y projection')):
            for a, b in edges:
                if state[a] == 2 and state[b] == 2 and np.isfinite(xy[[a, b]]).all():
                    ax.plot(xy[[a, b], horizontal], xy[[a, b], 1], color='#777777', linewidth=1.)
            for code, marker, color in ((2, 'o', '#0072B2'), (1, '^', '#D55E00'), (0, 'x', '#000000')):
                mask = (state == code) & np.isfinite(xy).all(1)
                ax.scatter(xy[mask, horizontal], xy[mask, 1], marker=marker, color=color, s=38)
            for i, point in enumerate(xy):
                if np.isfinite(point).all():
                    ax.annotate(str(i), (point[horizontal], point[1]), xytext=(4, 4), textcoords='offset points', fontsize=9)
            ax.set(xlabel=('X' if horizontal == 0 else 'Z')+' (m)', ylabel='Y (m)', title=title)
            ax.set_aspect('equal', adjustable='datalim')
            ax.grid(alpha=.2)
            ax.legend(handles=[Line2D([], [], color=c, marker=m, linestyle='none', label=t)
                for c, m, t in [('#0072B2', 'o', 'Tracked (observed)'), ('#D55E00', '^', 'Inferred (not observed)'),
                                 ('#000000', 'x', 'NotTracked coordinate (not evidence)')]], fontsize=9)
        fig.suptitle('IRDS Kinect25 mapping audit — raw coordinates, no smoothing', fontsize=15)
        output = export_figure(fig, destination / 'kinect_mapping', formats=['png', 'svg'], dpi=150,
            bbox_inches=None, write_manifest=True, provenance=dict(raw_data=str(data_path),
            source_sha256=file_hash(data_path), sample_rule='first sorted eligible sample, middle frame',
            transformations=['orthogonal projection only; links only when both endpoints observed'],
            uncertainty='not an estimate; one frame, not a population figure',
            missing_data='inferred/not-tracked marked; unknown coordinates never connected as evidence',
            intended_medium='offline developer audit, not a journal or product UI',
            alt_text='Two camera-axis projections of one public Kinect25 frame; numeric joint labels map to JSON names.'))
        plt.close(fig)
    # Matplotlib's SVG path serialization leaves harmless line-end spaces.
    # Formatting only: coordinates, labels and the PNG are not changed.
    for artifact in output['outputs']:
        if artifact['format'] == 'svg':
            svg = Path(artifact['path'])
            svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n', encoding='utf-8')
            artifact['size_bytes'] = svg.stat().st_size
    write_json(output['manifest'], output)
    return dict(path=str(destination / 'kinect_mapping.png'), source=str(data_path),
                matplotlib_version=matplotlib.__version__, export=output)
