"""Protect the original visual baseline, with explicit Qt control-code exceptions.

Does not refresh a baseline or make the earlier all-64-content check green.
Changed UI modules are reported separately; their untouched methods must retain
the original AST. Screenshots and UI behavior require additional inspection.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '05537bf51a16e2c839d0279dc606f4240d24befe'
PREFIX = 'rehab_codex_single_camera_v2_1/app/ui/'
ALLOWED = {
    PREFIX+'product_rehab.py': {'__init__', '_send', '_open_plan_library', '_library_command',
        '_open_practice_record', '_prepare_practice', '_resume_training_preparation', '_show_practice',
        'closeEvent', '_handle_message', '_open_report', '_export_selected', '_delete_report',
        '_open_longitudinal', '_compare'},
    PREFIX+'product_window.py': {'_render'},
    PREFIX+'product_completion.py': {'_history_detail', '_history_report', '_history_trends',
                                    '_completion_render', '_present_rehab', '_completion_controls'},
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def methods(data):
    parsed = ast.parse(data.decode('utf-8'))
    return {f'{node.name}.{method.name}': ast.dump(method, include_attributes=False)
            for node in parsed.body if isinstance(node, ast.ClassDef)
            for method in node.body if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    names = git('ls-tree', '-r', '--name-only', BASELINE, 'mobile_rehab/static', 'android_offline/res',
                PREFIX, 'rehab_codex_single_camera_v2_1/assets').decode().splitlines()
    suffixes = {'.css', '.qss', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.ttf', '.otf', '.woff', '.woff2', '.ico', '.xml'}
    names = [n for n in names if Path(n).suffix in suffixes or n.startswith(PREFIX)]
    results = []
    for name in names:
        old = git('show', BASELINE+':'+name); new = (ROOT/name).read_bytes()
        same = new == old or Path(name).suffix in {'.py', '.css', '.qss', '.svg', '.xml'} and new.replace(b'\r\n', b'\n') == old.replace(b'\r\n', b'\n')
        row = dict(path=name, unchanged=same, current_sha256=hashlib.sha256(new).hexdigest(),
                   baseline_blob_sha256=hashlib.sha256(old).hexdigest(), allowed_control_code_exception=name in ALLOWED)
        if not same and name in ALLOWED:
            before, after = methods(old), methods(new)
            row['non_authorized_method_changes'] = [key for key, value in before.items()
                if key.split('.')[-1] not in ALLOWED[name] and after.get(key) != value]
        results.append(row)
    new_ui = (ROOT/PREFIX/'guided_practice.py').read_text(encoding='utf-8')
    new_ui_has_visual_redefinition = any(token in new_ui for token in ('setStyleSheet(', 'QPalette(', 'QColor(', 'setFont(', 'setGeometry(', '.svg', '.png'))
    unauthorized = [r['path'] for r in results if not r['unchanged'] and (
        not r['allowed_control_code_exception'] or r.get('non_authorized_method_changes'))]
    result = dict(baseline_ref=BASELINE, original_protected_count=len(results),
                  unchanged_original_contents=sum(r['unchanged'] for r in results),
                  explicitly_changed_control_modules=[r['path'] for r in results if not r['unchanged'] and r['allowed_control_code_exception']],
                  unauthorized_changes=unauthorized, new_ui_has_visual_redefinition=new_ui_has_visual_redefinition,
                  screenshots_required=True, all_64_contents_unchanged=False,
                  passed=not unauthorized and not new_ui_has_visual_redefinition, files=results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, ensure_ascii=True))
    assert result['passed']


if __name__ == '__main__': main()
