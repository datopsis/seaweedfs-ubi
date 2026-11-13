#!/usr/bin/env python3
"""Keep one deferred-fix issue; notify only when the complete deferred set changes."""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

MARKER = '<!-- seaweedfs-ubi-repository-fix-tracker -->'
TITLE = 'UBI repository fix availability'
FIELDS = ('scanner', 'id', 'package', 'severity', 'installed', 'fixes')


def api(repo, endpoint, method='GET', payload=None):
    command = ['gh', 'api', f'repos/{repo}/{endpoint}']
    if method == 'GET':
        command += ['--paginate', '--slurp']
    else:
        command += ['--method', method, '--input', '-']
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True, check=True, timeout=60)
    return json.loads(result.stdout)


def state(directory):
    reports = [json.loads(path.read_text()) for path in directory.rglob('vulnerabilities.json')]
    result = []
    for arch in ('amd64', 'arm64'):
        matching = [r for r in reports if r.get('architecture') == arch]
        if len(matching) != 1:
            raise ValueError('missing or duplicate native evidence; retain previous issue state')
        report = matching[0]
        if report.get('schema_version') != 1 or 'error' in report or 'error' in report.get('query', {}):
            raise ValueError('invalid native evidence; retain previous issue state')
        rows = report.get('findings')
        if not isinstance(rows, list):
            raise ValueError('missing admission decisions')
        for row in rows:
            if not set(FIELDS) <= row.keys() or row.get('decision') not in ('block', 'deferred', 'unfixed'):
                raise ValueError('invalid admission decision')
            if row['decision'] == 'deferred':
                result.append(dict(architecture=arch, **{k: row[k] for k in FIELDS}))
    # Ignore ordering, duplicates, blocking/unfixed findings, timestamps and run IDs.
    return [json.loads(s) for s in sorted({json.dumps(r, sort_keys=True) for r in result})]


def cell(value):
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')


def render(rows, run_url):
    fingerprint = '<!-- deferred-sha256:' + hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest() + ' -->'
    lines = [MARKER, fingerprint, '', 'RPM vendor fixes not yet published in the configured UBI repositories.',
             'Deferred findings remain vulnerabilities. An installable fix blocks the next gate.', '',
             f'[Native CI evidence]({run_url})', '',
             'Architecture | Scanner | Finding | Package | Severity | Installed | Vendor fixed version',
             '--- | --- | --- | --- | --- | --- | ---']
    for row in rows:
        lines.append(' | '.join(cell(row[k]) for k in ('architecture',) + FIELDS[:-1]) + ' | ' + cell(', '.join(row['fixes'])))
    if not rows:
        lines += ['', 'No deferred RPM fixes. Blocking and unfixed findings remain in CI evidence; this is not a clean bill of health.']
    return '\n'.join(lines) + '\n', fingerprint


def update(repo, rows, run_url, call=api):
    body, fingerprint = render(rows, run_url)
    pages = call(repo, 'issues?state=all&per_page=100')
    issues = [i for page in pages for i in page if not i.get('pull_request') and MARKER in (i.get('body') or '')]
    if len(issues) > 1:
        raise ValueError('multiple tracking issues; refusing to create another')
    if not issues:
        return call(repo, 'issues', 'POST', {'title': TITLE, 'body': body}) if rows else None
    issue = issues[0]
    desired = 'open' if rows else 'closed'
    if fingerprint not in issue['body']:
        call(repo, f'issues/{issue["number"]}/comments', 'POST', {'body': 'Deferred set changed.\n\n' + body})
        return call(repo, f'issues/{issue["number"]}', 'PATCH', {'body': body, 'state': desired})
    if issue['state'] != desired:
        return call(repo, f'issues/{issue["number"]}', 'PATCH', {'state': desired})
    return issue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    rows = state(args.directory)
    repo = os.environ['GITHUB_REPOSITORY']
    run_url = f'https://github.com/{repo}/actions/runs/{os.environ["GITHUB_RUN_ID"]}'
    if args.dry_run:
        print(render(rows, run_url)[0])
    else:
        if os.environ.get('GITHUB_EVENT_NAME') != 'schedule' or os.environ.get('GITHUB_REF') != 'refs/heads/main':
            raise ValueError('issue updates require a scheduled main-branch run')
        print(json.dumps(update(repo, rows, run_url)))


if __name__ == '__main__':
    main()
