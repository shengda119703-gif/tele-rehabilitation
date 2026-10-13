"""Own real HTTP service and run the current browser UI suite."""
import argparse
from pathlib import Path
import subprocess
from ankang_care_blackbox import Run, ROOT

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);run=Run(a.output/'service')
    try:
        run.start()
        result=subprocess.run(['node',str(ROOT/'tools/qa/comprehensive-web.cjs'),f'http://127.0.0.1:{run.port}',str(a.output/'browser')],cwd=ROOT,capture_output=True,encoding='utf-8',timeout=300)
        (a.output/'browser.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        print(result.stdout)
        if result.returncode:print(result.stderr)
        return result.returncode
    finally:run.stop()

if __name__=='__main__':raise SystemExit(main())
