"""Install both built distributions into isolated environments and exercise CLI."""
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv

root = Path(__file__).resolve().parents[1]
artifacts = list((root / 'dist').glob('*.whl')) + list((root / 'dist').glob('*.tar.gz'))
if len(artifacts) != 2:
    raise SystemExit('Expected one wheel and one sdist')
env = dict(os.environ)
env.pop('PYTHONPATH', None)
env.pop('PYTHONHOME', None)
for artifact in artifacts:
    with tempfile.TemporaryDirectory(prefix='gage-window-dist-') as folder:
        base = Path(folder)
        venv.create(base / 'venv', with_pip=True)
        python = base / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        def run(*args, expected=0):
            result = subprocess.run([str(python), *map(str,args)], cwd=base, env=env, capture_output=True, text=True)
            if result.returncode != expected:
                raise RuntimeError(f'{args}: exit {result.returncode}\n{result.stdout}\n{result.stderr}')
            return result.stdout
        run('-m', 'pip', 'install', '--no-deps', artifact)
        location = run('-c', 'import gage_window; print(gage_window.__file__)').strip()
        assert str(base / 'venv') in location, location
        shutil.copytree(root / 'tests', base / 'tests', ignore=shutil.ignore_patterns('__pycache__'))
        env['GAGE_WINDOW_INSTALLED'] = '1'
        run('-m', 'unittest', 'discover', '-s', base / 'tests', '-v')
        run('-m', 'gage_window', 'example', 'example')
        run('-m', 'gage_window', 'analyze', 'example/project.json', '--out', 'report', expected=2)
        analysis = json.loads((base / 'report/analysis.json').read_text())
        assert len(analysis['records']) == 9 and len(analysis['cases']) == 6
        assert analysis['counts'] == {'other_gage': 1, 'outside_window': 2, 'possible_overlap': 2, 'recorded_overlap': 1, 'unresolved': 3}
        run('-m', 'gage_window', 'verify', 'report')
        with (base / 'report/cases.csv').open(newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream); headers = reader.fieldnames; rows = list(reader)
        for row in rows:
            row.update(status='escalated',owner='Constructed reviewer',rationale='Human follow-up assigned',evidence='EXAMPLE-1')
        with (base / 'decisions.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream,fieldnames=headers);writer.writeheader();writer.writerows(rows)
        run('-m', 'gage_window', 'review', 'report', '--decisions', 'decisions.csv', '--out', 'reviewed')
        (base / 'report').rename(base / 'relocated')
        run('-m', 'gage_window', 'verify', 'relocated')
        run('-m', 'gage_window', 'verify', 'reviewed')
        run('-m', 'gage_window', 'analyze', 'example/project.json', '--out', 'reviewed', expected=1)
        print(f'PASS: {artifact.name}: isolated install, exact example counts, review, relocation, refusal')
