"""Deterministic evidence accounting. Inputs are assertions, never ground truth."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from . import __version__

MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 50_000
MAX_CELL = 4096
IMMUTABLE = ['analysis_id', 'case_id', 'work_id', 'record_ids', 'window_ids']
EDITABLE = ['status', 'owner', 'rationale', 'evidence']
NOTICE = ('Evidence review only. Recorded candidates are not a determination of affected product. '
          'Custody is not proof of measurement. Unlogged use cannot be recovered; no matching recorded '
          'use in supplied exports does not establish no exposure. Humans choose review windows and '
          'make all engineering, containment, conformance and release decisions.')
STAMP = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$')
DAY = re.compile(r'^\d{4}-\d{2}-\d{2}$')


class InputError(ValueError):
    """A user-actionable contract violation."""


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path, limit=MAX_BYTES):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise InputError(f'Expected regular, non-symlink file: {path.name}')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise InputError(f'File exceeds {limit} byte limit: {path.name}')
    return data


def unique_object(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise InputError(f'Duplicate JSON key: {k}')
        result[k] = v
    return result


def parse_json(data):
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=unique_object,
                          parse_constant=lambda x: (_ for _ in ()).throw(InputError('Nonfinite JSON')))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise InputError('Invalid UTF-8 JSON') from exc


def exact_keys(obj, required, optional=()):
    if not isinstance(obj, dict) or not set(required) <= set(obj) or set(obj) - set(required) - set(optional):
        raise InputError(f'Expected object keys {required}; optional {optional}')


def label(value, what):
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_CELL or not value.isprintable():
        raise InputError(f'{what} must be a nonempty printable string <=4096 characters')
    return value


def stamp(value):
    if not isinstance(value, str) or not STAMP.fullmatch(value):
        raise InputError('Expected timestamp YYYY-MM-DDTHH:MM:SS[.ffffff]Z or +/-HH:MM')
    try:
        # fromisoformat accepts offsets beyond 23:59 inconsistently; reject explicitly.
        if not value.endswith('Z'):
            hours, minutes = map(int, value[-5:].split(':'))
            if hours > 23 or minutes > 59:
                raise ValueError('offset')
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise InputError('Invalid or unrepresentable timestamp') from exc


def bounds(value):
    if DAY.fullmatch(value):
        try:
            low = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
            return low, low + timedelta(days=1) - timedelta(microseconds=1)
        except (ValueError, OverflowError) as exc:
            raise InputError('Invalid or unrepresentable UTC day') from exc
    t = stamp(value)
    return t, t


def iso(t):
    return t.isoformat().replace('+00:00', 'Z') if t is not None else None


def validate_project(project):
    exact_keys(project, ['schema_version', 'gages', 'aliases', 'windows', 'sources'])
    if type(project['schema_version']) is not int or project['schema_version'] != 1:
        raise InputError('Unsupported schema_version (expected 1)')
    gages = project['gages']
    if not isinstance(gages, list) or not 1 <= len(gages) <= 10000:
        raise InputError('gages requires 1..10000 unique IDs')
    for g in gages:
        label(g, 'gage ID')
    if len(set(gages)) != len(gages):
        raise InputError('Duplicate canonical gage ID')
    aliases = project['aliases']
    if not isinstance(aliases, dict) or len(aliases) > 10000:
        raise InputError('aliases must be an object with <=10000 entries')
    for alias, g in aliases.items():
        label(alias, 'alias')
        if g not in gages or alias in gages:
            raise InputError('Aliases must map noncanonical exact spellings directly to canonical IDs')
    windows = project['windows']
    if not isinstance(windows, list) or not 1 <= len(windows) <= 32:
        raise InputError('windows requires 1..32 entries')
    ids = set()
    for w in windows:
        exact_keys(w, ['id', 'gage_id', 'start', 'end', 'reason'])
        label(w['id'], 'window ID'); label(w['reason'], 'window reason')
        if w['id'] in ids or w['gage_id'] not in gages:
            raise InputError('Duplicate window ID or unknown window gage')
        ids.add(w['id'])
        if stamp(w['start']) > stamp(w['end']):
            raise InputError('Window end precedes start')
    sources = project['sources']
    if not isinstance(sources, list) or not 1 <= len(sources) <= 16:
        raise InputError('sources requires 1..16 entries')
    names = set()
    for s in sources:
        exact_keys(s, ['name', 'path', 'kind', 'columns'])
        label(s['name'], 'source name'); label(s['path'], 'source path')
        if s['name'] in names or s['kind'] not in ('direct', 'custody'):
            raise InputError('Duplicate source name or invalid kind (direct/custody)')
        names.add(s['name'])
        exact_keys(s['columns'], ['gage_id', 'work_id', 'start'], ['end', 'reference'])
        for col in s['columns'].values():
            label(col, 'column name')
        if len(set(s['columns'].values())) != len(s['columns']):
            raise InputError('Column mappings must be distinct')
    return project


def parse_csv(data, worksheet=False):
    field_limit = 4 * 1024 * 1024 if worksheet else MAX_CELL
    previous_limit = csv.field_size_limit(field_limit)
    try:
        text = data.decode('utf-8-sig')
        if '\x00' in text:
            raise InputError('CSV contains NUL')
        rows = []
        for row in csv.reader(io.StringIO(text, newline=''), strict=True):
            if len(rows) > MAX_ROWS:
                raise InputError('CSV exceeds 50000 records')
            if len(row) > 128 or any(len(cell) > field_limit for cell in row):
                raise InputError('CSV exceeds column or cell resource limit')
            rows.append(row)
    except (UnicodeError, csv.Error) as exc:
        raise InputError('Invalid UTF-8 CSV') from exc
    finally:
        csv.field_size_limit(previous_limit)
    if not rows:
        raise InputError('CSV is missing its header')
    headers = rows[0]
    if not headers or any(not x.strip() for x in headers) or len(set(headers)) != len(headers):
        raise InputError('CSV headers must be nonempty and unique')
    if len(headers) > 128:
        raise InputError('CSV exceeds 128 columns')
    if len(rows) - 1 > MAX_ROWS:
        raise InputError('CSV exceeds 50000 records')
    return headers, rows[1:]


def classify(project, sources):
    """sources: list of bytes corresponding to validated project source descriptions."""
    records = []
    evidence_bytes = 0
    source_hashes = []
    window_times = [(w, stamp(w['start']), stamp(w['end'])) for w in project['windows']]
    suspect = {w['gage_id'] for w in project['windows']}
    for index, (source, data) in enumerate(zip(project['sources'], sources)):
        headers, rows = parse_csv(data)
        if any(c not in headers for c in source['columns'].values()):
            raise InputError(f"Mapped column missing in source {source['name']}")
        source_hash = digest(data)
        source_hashes.append({'name': source['name'], 'sha256': source_hash, 'file': f'input-{index:02d}.csv'})
        seen = set()
        for number, cells in enumerate(rows, 2):
            if len(records) >= MAX_ROWS:
                raise InputError('Project exceeds 50000 total records')
            raw = {h: cells[i] if i < len(cells) else '' for i, h in enumerate(headers)}
            # Preserve extra cells under a separate key instead of silently truncating.
            reasons = []
            if len(cells) != len(headers):
                reasons.append('row_width_mismatch')
            row_key = canonical(cells)
            if row_key in seen:
                reasons.append('duplicate_source_row_retained')
            seen.add(row_key)
            get = lambda field: raw.get(source['columns'].get(field, ''), '')
            gage = get('gage_id')
            gage = project['aliases'].get(gage, gage)
            known = gage in project['gages']
            work = get('work_id')
            low = high = None
            time_valid = True
            try:
                low, start_latest = bounds(get('start'))
                end_text = get('end')
                if end_text:
                    end_earliest, high = bounds(end_text)
                    if high < low:
                        raise InputError('End precedes start')
                else:
                    high = start_latest if source['kind'] == 'direct' else None
            except InputError:
                time_valid = False
                reasons.append('missing_invalid_or_reversed_time')
            matches = []
            contained = False
            if known and gage not in suspect:
                category = 'other_gage'
            elif not known:
                category = 'unresolved'
                reasons.append('unknown_or_missing_gage')
            elif not time_valid or 'row_width_mismatch' in reasons:
                category = 'unresolved'
            else:
                for w, start, end in window_times:
                    if w['gage_id'] == gage and low <= end and (high is None or high >= start):
                        matches.append(w['id'])
                        if high is not None and low >= start and high <= end:
                            contained = True
                if not matches:
                    category = 'outside_window'
                elif source['kind'] == 'direct' and contained:
                    category = 'recorded_overlap'
                else:
                    category = 'possible_overlap'
                    reasons.append('custody_not_measurement' if source['kind'] == 'custody' else 'partial_or_imprecise_overlap')
                if matches and not work.strip():
                    category = 'unresolved'
                    reasons.append('missing_work_id')
            if 'row_width_mismatch' in reasons:
                category = 'unresolved'
            rid = digest(canonical([source['name'], source_hash, number]))
            record = {'record_id': rid, 'source': source['name'], 'row': number,
                            'raw': raw, 'extra_cells': cells[len(headers):], 'kind': source['kind'], 'gage_id': gage, 'work_id': work,
                            'start': iso(low) if time_valid else None,
                            'end': iso(high) if time_valid else None,
                            'classification': category, 'window_ids': matches, 'reasons': reasons}
            # Bound expansion before retaining records or rendering repeated headers/cases.
            evidence_bytes += len(canonical(record))
            if evidence_bytes > 8 * 1024 * 1024:
                raise InputError('Expanded row evidence exceeds 8 MiB; split the investigation into smaller projects')
            records.append(record)
    groups = defaultdict(list)
    for row in records:
        if row['classification'] in ('recorded_overlap', 'possible_overlap', 'unresolved'):
            key = ('work', row['work_id']) if row['work_id'].strip() else ('record', row['record_id'])
            groups[key].append(row)
    cases = []
    for key in sorted(groups):
        group = groups[key]
        cases.append({'case_id': digest(canonical(key)), 'work_id': group[0]['work_id'],
                      'record_ids': [r['record_id'] for r in group],
                      'window_ids': sorted({w for r in group for w in r['window_ids']})})
    result = {'schema_version': 1, 'tool_version': __version__, 'project': project,
              'source_hashes': source_hashes, 'records': records, 'cases': cases,
              'counts': dict(sorted(Counter(r['classification'] for r in records).items()))}
    result['analysis_id'] = digest(canonical(result))
    return result


def safe_cell(value):
    value = str(value)
    if value.startswith("'") or value.lstrip().startswith(('=', '+', '-', '@')) or any(c in value[:1] for c in '\t\r\n'):
        return "'" + value
    return value


def original_cell(value):
    if value.startswith("'") and safe_cell(value[1:]) == value:
        return value[1:]
    return value


def csv_bytes(headers, rows):
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(headers)
    for row in rows:
        writer.writerow([safe_cell(row.get(h, '')) for h in headers])
    return output.getvalue().encode('utf-8')


def case_rows(analysis):
    return [{'analysis_id': analysis['analysis_id'], **{k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k, v in c.items()},
             'status': 'open', 'owner': '', 'rationale': '', 'evidence': ''} for c in analysis['cases']]


def render(analysis, decisions=None):
    esc = lambda x: html.escape(str(x), quote=True)
    counts = ' · '.join(f'{esc(k)}: {v}' for k, v in analysis['counts'].items()) or 'No data records supplied'
    decision_map = {r['case_id']: r for r in decisions or []}
    case_html = ''.join('<tr>' + ''.join(f'<td>{esc(value)}</td>' for value in
                          [c['work_id'] or '(missing work ID)', c['case_id'], len(c['record_ids']),
                           ', '.join(c['window_ids']), decision_map.get(c['case_id'], {}).get('status', 'open'),
                           decision_map.get(c['case_id'], {}).get('owner', ''),
                           decision_map.get(c['case_id'], {}).get('rationale', ''),
                           decision_map.get(c['case_id'], {}).get('evidence', '')]) + '</tr>' for c in analysis['cases'])
    records_html = ''.join('<tr>' + ''.join(f'<td>{esc(value)}</td>' for value in
                             [r['source'], r['row'], r['gage_id'], r['work_id'], r['kind'], r['classification'],
                              r['start'], r['end'], ', '.join(r['window_ids']), ', '.join(r['reasons']),
                              json.dumps({'cells': r['raw'], 'surplus_cells': r['extra_cells']}, ensure_ascii=False)]) + '</tr>' for r in analysis['records'])
    windows_html = ''.join(f'<li><strong>{esc(w["id"])}</strong> — {esc(w["gage_id"])}: {esc(w["start"])} through {esc(w["end"])}. {esc(w["reason"])}</li>' for w in analysis['project']['windows'])
    def table(heads, body):
        return '<div class="scroll" tabindex="0" role="region" aria-label="Scrollable evidence table"><table><thead><tr>' + ''.join(f'<th scope="col">{h}</th>' for h in heads) + '</tr></thead><tbody>' + body + '</tbody></table></div>'
    return (f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            f'<title>gage-window evidence review</title><style>body{{font:16px/1.5 system-ui,sans-serif;color:#182f38;background:#f5f7f5;margin:0}}'
            f'main{{max-width:1200px;margin:auto;padding:24px}}h1{{font-size:2rem}}.notice{{border-left:5px solid #a65a15;background:#fff1dc;padding:16px}}'
            f'.identity{{overflow-wrap:anywhere}}.scroll{{overflow:auto;max-height:65vh;background:white;border:1px solid #b6c4c6;margin:16px 0}}'
            f'table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:10px;border:1px solid #ced8da;text-align:left;vertical-align:top;min-width:110px;max-width:420px;overflow-wrap:anywhere}}'
            f'th{{background:#173f48;color:white}}.scroll:focus{{outline:3px solid #a65a15}}@media print{{.scroll{{max-height:none;overflow:visible}}main{{padding:0}}table{{font-size:10px}}}}</style>'
            f'<main><p>GAGE-WINDOW / EVIDENCE REVIEW</p><h1>Reconcile the record. Preserve the uncertainty.</h1><p class="notice">{esc(NOTICE)}</p>'
            f'<p class="identity">Analysis: {esc(analysis["analysis_id"])}<br>Tool version: {esc(analysis["tool_version"])}</p>'
            f'<h2>Supplied evidence</h2><p>{len(analysis["records"])} records · {len(analysis["cases"])} review cases</p><p>{counts}</p>'
            f'<p>Review status records human follow-up only. “Reviewed” and “escalated” do not establish product conformance or investigation approval.</p>'
            f'<h2>Human-selected windows (inclusive)</h2><ul>{windows_html}</ul><h2>Review cases</h2>' +
            table(['Work / lot', 'Case ID', 'Records', 'Windows', 'Status', 'Owner', 'Rationale', 'Evidence'], case_html) +
            '<h2>Every supplied record</h2><p>Row numbers are logical CSV records; quoted multiline cells count as one record. Null end on custody means open-ended.</p>' +
            table(['Source', 'Row', 'Gage', 'Work', 'Evidence kind', 'Classification', 'Earliest start (UTC)', 'Latest end (UTC)', 'Windows', 'Reasons', 'Original cells'], records_html) + '</main></html>').encode('utf-8')


def make_files(analysis, sources, decisions=None):
    files = {'analysis.json': json.dumps(analysis, indent=2, ensure_ascii=False).encode('utf-8') + b'\n',
             'cases.csv': csv_bytes(IMMUTABLE + EDITABLE, case_rows(analysis)),
             'report.html': render(analysis, decisions)}
    flat = [{**r, 'window_ids': json.dumps(r['window_ids'], ensure_ascii=False),
             'reasons': json.dumps(r['reasons'], ensure_ascii=False), 'raw': json.dumps(r['raw'], ensure_ascii=False),
             'extra_cells': json.dumps(r['extra_cells'], ensure_ascii=False)} for r in analysis['records']]
    files['records.csv'] = csv_bytes(['record_id', 'source', 'row', 'gage_id', 'work_id', 'kind', 'start', 'end', 'classification', 'window_ids', 'reasons', 'raw', 'extra_cells'], flat)
    files.update({s['file']: data for s, data in zip(analysis['source_hashes'], sources)})
    if decisions is not None:
        files['decisions.csv'] = csv_bytes(IMMUTABLE + EDITABLE, decisions)
    files['manifest.json'] = json.dumps({'schema_version': 1, 'files': {name: digest(data) for name, data in sorted(files.items())}}, indent=2).encode('utf-8') + b'\n'
    return files


def publish(out, files):
    out = Path(out)
    if out.exists() or out.is_symlink():
        raise InputError('Output path already exists; choose a new directory')
    if not out.parent.is_dir():
        raise InputError('Output parent directory does not exist')
    if any(len(data) > 256 * 1024 * 1024 for data in files.values()) or sum(map(len, files.values())) > 512 * 1024 * 1024:
        raise InputError('Generated report exceeds 256 MiB per file or 512 MiB combined limit')
    temp = Path(tempfile.mkdtemp(prefix='.gage-window-', dir=out.parent))
    try:
        for name, data in files.items():
            (temp / name).write_bytes(data)
        # mkdir reserves the destination without replacing a concurrent writer.
        out.mkdir()
        try:
            for name in files:
                os.replace(temp / name, out / name)
        except BaseException:
            shutil.rmtree(out)
            raise
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def analyze(path, out):
    path = Path(path)
    project = validate_project(parse_json(read_bytes(path)))
    sources = [read_bytes(path.parent / s['path']) for s in project['sources']]
    if sum(map(len, sources)) > MAX_BYTES:
        raise InputError('Combined CSV sources exceed 20 MiB')
    # Snapshot paths are portable, and absolute source paths never leak to the report.
    project = parse_json(canonical(project))
    for i, s in enumerate(project['sources']):
        s['path'] = f'input-{i:02d}.csv'
    analysis = classify(project, sources)
    publish(out, make_files(analysis, sources))
    return analysis


def validate_decisions(analysis, data):
    headers, rows = parse_csv(data, worksheet=True)
    if headers != IMMUTABLE + EDITABLE:
        raise InputError('Decision worksheet columns/order changed')
    expected = {c['case_id']: c for c in case_rows(analysis)}
    found = {}
    decisions = []
    for cells in rows:
        if len(cells) != len(headers):
            raise InputError('Decision worksheet row width changed')
        row = dict(zip(headers, cells))
        cid = row['case_id']
        if cid not in expected or cid in found:
            raise InputError('Unexpected or duplicate case ID')
        if any(row[k] != safe_cell(expected[cid][k]) for k in IMMUTABLE):
            raise InputError('Stale or altered worksheet identity; regenerate for this analysis')
        for key in EDITABLE:
            row[key] = original_cell(row[key])
            if len(row[key]) > MAX_CELL:
                raise InputError('Editable decision fields exceed 4096 characters')
        if row['status'] not in ('open', 'reviewed', 'escalated'):
            raise InputError('Status must be open, reviewed or escalated')
        if row['status'] != 'open' and not all(row[k].strip() for k in ('owner', 'rationale', 'evidence')):
            raise InputError('Non-open cases require owner, rationale and evidence')
        found[cid] = True
        decisions.append({**expected[cid], **{k: row[k] for k in EDITABLE}})
    if set(found) != set(expected):
        raise InputError('Missing decision cases; every case must be returned')
    return sorted(decisions, key=lambda r: r['case_id'])


def verify(directory):
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise InputError('Expected report directory (not symlink)')
    manifest = parse_json(read_bytes(directory / 'manifest.json'))
    exact_keys(manifest, ['schema_version', 'files'])
    if manifest['schema_version'] != 1 or not isinstance(manifest['files'], dict):
        raise InputError('Invalid manifest')
    # Never read paths supplied by an untrusted manifest before enforcing a fixed allowlist.
    allowed = {'analysis.json', 'cases.csv', 'records.csv', 'report.html', 'decisions.csv'} | {f'input-{i:02d}.csv' for i in range(16)}
    names = set(manifest['files'])
    if not names <= allowed or {p.name for p in directory.iterdir()} != names | {'manifest.json'}:
        raise InputError('Unexpected or missing report files')
    if sum(p.stat().st_size for p in directory.iterdir()) > 512 * 1024 * 1024:
        raise InputError('Report exceeds 512 MiB')
    actual = {n: read_bytes(directory / n, 256 * 1024 * 1024) for n in names}
    if any(digest(data) != manifest['files'][n] for n, data in actual.items()):
        raise InputError('Report integrity mismatch')
    if 'analysis.json' not in actual:
        raise InputError('Missing analysis.json')
    analysis = parse_json(actual['analysis.json'])
    exact_keys(analysis, ['schema_version', 'tool_version', 'project', 'source_hashes', 'records', 'cases', 'counts', 'analysis_id'])
    if analysis['tool_version'] != __version__:
        raise InputError('Report must be verified with the producing tool version')
    project = validate_project(analysis['project'])
    paths = [f'input-{i:02d}.csv' for i in range(len(project['sources']))]
    if [s['path'] for s in project['sources']] != paths or not set(paths) <= names:
        raise InputError('Invalid source snapshot names')
    sources = [actual[n] for n in paths]
    if sum(map(len, sources)) > MAX_BYTES:
        raise InputError('Combined CSV sources exceed 20 MiB')
    regenerated = classify(project, sources)
    if regenerated != analysis:
        raise InputError('Analysis does not reproduce from its supplied evidence')
    decisions = validate_decisions(analysis, actual['decisions.csv']) if 'decisions.csv' in names else None
    expected_files = make_files(analysis, sources, decisions)
    if actual != {n: d for n, d in expected_files.items() if n != 'manifest.json'}:
        raise InputError('Report outputs do not reproduce')
    return analysis, sources, decisions


def review(directory, decisions_path, out):
    analysis, sources, _ = verify(directory)
    decisions = validate_decisions(analysis, read_bytes(decisions_path, 256 * 1024 * 1024))
    publish(out, make_files(analysis, sources, decisions))
    return decisions
