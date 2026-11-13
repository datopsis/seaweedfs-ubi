"""Repository-aware decisions; adapted from sail-ubi commit 861d92f."""
from urllib.parse import parse_qs, unquote, urlsplit


def rpm_arch(purl, name):
    """Only positively identified Red Hat RPMs can use repository deferral."""
    if not isinstance(purl, str):
        return None
    parsed = urlsplit(purl)
    if parsed.scheme != 'pkg' or not parsed.path.startswith('rpm/redhat/'):
        return None
    package = parsed.path.removeprefix('rpm/redhat/').split('@', 1)
    if len(package) != 2 or unquote(package[0]) != name:
        return None
    arch = parse_qs(parsed.query).get('arch', [])
    return arch[0] if len(arch) == 1 else None


def classify(rows, arch, query=None):
    requests, pending = [], []
    expected_arch = {'amd64': 'x86_64', 'arm64': 'aarch64'}.get(arch)
    for row in rows:
        row['decision'] = 'unfixed'
        row['reason'] = 'scanner reports no fix'
        if not row['fix_reported']:
            continue
        row['decision'] = 'block'
        row['reason'] = 'fixed non-RPM or unverified RPM identity/architecture'
        if row['rpm'] and expected_arch and row['package_arch'] in [expected_arch, 'noarch']:
            row['reason'] = 'repository query not completed'
            requests.append({'name': row['package'], 'fixes': row['fixes']})
            pending.append(row)
    evidence = {}
    if query is None:
        evidence = {'error': 'repository query not configured'} if requests else {}
    else:
        try:
            evidence = query(requests, arch)
            if not isinstance(evidence.get('repositories'), dict) or not evidence['repositories'].get('urls'):
                raise ValueError('missing repository provenance')
            results = evidence['results']
            if len(results) != len(pending):
                raise ValueError('incomplete repository query response')
            for row, result in zip(pending, results):
                if result.get('error'):
                    raise ValueError('repository query error: ' + str(result['error']))
                elif type(result.get('available')) is not bool or not isinstance(result.get('candidates'), list):
                    raise ValueError('invalid repository query response')
                else:
                    row['candidates'] = result['candidates']
                    row['decision'] = 'block' if result['available'] else 'deferred'
                    row['reason'] = ('fixed RPM available from UBI' if result['available'] else
                                     'vendor fix not yet available from UBI repositories')
        except Exception as error:
            # Reset every pending row even if an error occurred after a partial response.
            for row in pending:
                row['decision'] = 'block'
                row['reason'] = f'repository query failed ({type(error).__name__}): {error}'
            evidence = {'error': str(error)}
    return rows, evidence


def cell(value):
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')


def summary(rows, arch):
    lines = [f'### Vulnerability admission ({cell(arch or "architecture unspecified")})', '',
             'Deferred RPM findings still affect this image; they are not remediated or suppressed.', '',
             'Scanner | ID | Package | Severity | Vendor fixed version | Decision | Reason',
             '--- | --- | --- | --- | --- | --- | ---']
    for row in rows:
        fixed = ', '.join(row['fixes']) or ('unspecified' if row['fix_reported'] else 'no fix reported')
        lines.append(' | '.join(cell(v) for v in [row['scanner'], row['id'], row['package'], row['severity'],
                                                fixed, row['decision'], row['reason']]))
    return '\n'.join(lines) + '\n'
