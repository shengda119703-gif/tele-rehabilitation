from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

from .common import ROOT, file_hash, git, paths, read_json, utc_now, write_json

# Existing behavior is frozen; only explicit host wiring is allowed in later stages.
ALLOW_EXISTING = {'mobile_rehab/server.py', 'docs/HANDOFF.md'}


def source_files():
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z',
                                   '--cached', '--others', '--exclude-standard'])
    return {p.decode('utf-8').replace('\\', '/') for p in raw.split(b'\0') if p}


def protected_files():
    candidates = {p for p in source_files() if (
        p.startswith(('rehab_codex_single_camera_v2_1/', 'mobile_rehab/', 'android_offline/',
                      'agent/', 'agent_bridge/', 'packages/', 'frontend/', 'web/'))
        and p not in ALLOW_EXISTING
        and not p.startswith(('rehab_codex_single_camera_v2_1/app/rehab_v2/',
                              'mobile_rehab/rehab_v2/', 'tools/rehab_ml/')))}
    # Entire APK directory, including ignored artifacts and dependency caches, is read-only.
    for path in (ROOT / 'android_offline').rglob('*'):
        if path.is_file():
            candidates.add(path.relative_to(ROOT).as_posix())
    # Protect baseline models even though Git ignores the weights.
    for path in (ROOT / 'rehab_codex_single_camera_v2_1/assets/models').glob('*'):
        if path.is_file():
            candidates.add(path.relative_to(ROOT).as_posix())
    return sorted(p for p in candidates if (ROOT / p).is_file())


def doctor():
    dependencies = {}
    for name in ('numpy', 'torch', 'PySide6', 'requests', 'PyYAML', 'ultralytics'):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = None
    return dict(python=sys.version, executable=sys.executable, platform=platform.platform(),
                dependencies=dependencies, roots={k: str(v) for k, v in paths().items()},
                disk={drive: shutil.disk_usage(drive)._asdict()
                      for drive in ('C:/', 'D:/', 'E:/') if Path(drive).exists()},
                git_commit=git('rev-parse', 'HEAD'))


def legacy_replay():
    app = ROOT / 'rehab_codex_single_camera_v2_1'
    started = time.perf_counter()
    proc = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest', 'discover',
                           '-s', 'tests', '-p', 'test_app_rehab.py', '-v'],
                          cwd=app, capture_output=True, text=True, encoding='utf-8', timeout=90)
    log = paths()['run'] / 'inventory' / 'legacy-replay.txt'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(proc.stdout + proc.stderr, encoding='utf-8')
    result = dict(exit_code=proc.returncode, elapsed_s=time.perf_counter()-started,
                  log=str(log), log_sha256=file_hash(log), kind='deterministic_legacy_backend_replay',
                  clinical_accuracy=None, camera_validation=False)
    if proc.returncode:
        raise RuntimeError('Legacy replay failed: ' + str(log))
    return result


def inventory():
    baseline = ROOT / 'reports/rehab_backend/protected_files.json'
    if baseline.exists():
        raise FileExistsError('Baseline already exists; verify it rather than replacing protection evidence')
    dirty = git('status', '--porcelain=v1', '-uall')
    started = time.perf_counter()
    protected = {name: dict(sha256=file_hash(ROOT / name), bytes=(ROOT / name).stat().st_size)
                 for name in protected_files()}
    metadata = doctor()
    replay = legacy_replay()
    value = dict(version=1, captured_at=utc_now(), git_commit=metadata['git_commit'],
                 dirty_before=dirty.splitlines(), protected=protected,
                 allowed_existing=sorted(ALLOW_EXISTING),
                 protected_new_file_roots=['android_offline/', 'mobile_rehab/static/'],
                 android_entire_directory=True, hash_elapsed_s=time.perf_counter()-started,
                 environment=metadata, legacy_replay=replay)
    write_json(baseline, value)
    report = ROOT / 'reports/rehab_backend_inventory.md'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text('# 康复后端 P0 开工清单\n\n'
        f"采集时间：{value['captured_at']}；基准：`{value['git_commit']}`。\n\n"
        f"保护 {len(protected)} 个文件（包含整个 android_offline 的忽略产物）；"
        '完整 hash、原有未提交改动和环境见 `rehab_backend/protected_files.json`。\n\n'
        '## 范围\n\n'
        '只新增 app/rehab_v2、康复会话宿主、tools/rehab_ml、configs/rehab_ml 和后端测试。'
        '旧域对象、PoseAnalyzer、GuidancePolicy、TrainingEngine、Storage 和所有界面冻结；'
        '新协议通过独立版本入口复用原域对象与分析器。旧 live 仍只预览。\n\n'
        '## 当前入口与复用\n\n'
        '- app/runtime.py：桌面原采集及训练；本轮不改入口和 UI。\n'
        '- mobile_rehab/server.py、live.py：既有认证、隔离推理；新会话须 opt-in，不能改旧 live 语义。\n'
        '- app/quality.py：原图像素、逐点 EMA、分指标测量；肩主角度只依赖肩和肘。\n'
        '- app/rehab.py、training.py：旧动作计数与训练；新协议解决坐站首帧、遮挡转折和计数/质量分离。\n'
        '- app/storage.py：单线程 SQLite v4；任何新表使用同一 owning thread，隔离库验收。\n'
        '- app/guidance.py：复用原下一步提示策略；另加有时效的结构化事件。\n\n'
        '## 基线与机器\n\n'
        f"旧康复/坐站后端回放 exit={replay['exit_code']}，{replay['elapsed_s']:.3f} 秒，"
        f"日志 `{replay['log']}`，SHA256 `{replay['log_sha256']}`。这是确定性回归，不是真人准确度。\n\n"
        '环境与依赖：\n\n```json\n' + json.dumps(metadata, ensure_ascii=False, indent=2) + '\n```\n',
        encoding='utf-8')
    return dict(baseline=str(baseline), report=str(report), file_count=len(protected), replay=replay)


def verify_scope(baseline):
    value = read_json(baseline)
    changes = []
    for name, before in value['protected'].items():
        path = ROOT / name
        if not path.is_file():
            changes.append(dict(path=name, reason='removed'))
        elif file_hash(path) != before['sha256']:
            changes.append(dict(path=name, reason='changed'))
    protected_names = set(value['protected'])
    for path in protected_files():
        if path not in protected_names:
            changes.append(dict(path=path, reason='added_to_protected_scope'))
    result = dict(ok=not changes, checked=len(protected_names), changes=changes,
                  baseline_sha256=file_hash(baseline), verified_at=utc_now())
    write_json(ROOT / 'reports/rehab_backend/scope_verification.json', result)
    if changes:
        raise RuntimeError('Protected scope changed: ' + json.dumps(changes, ensure_ascii=False))
    return result
