"""Fail-closed validation of the bounded Phase A four-role fixture profile.

This is a host-side preflight, not a runtime image guard or TLS qualification.
Only this exact rendered recipe is admitted; native gRPC hostname policy still
blocks Phase A. No third-party Python packages or image changes are required.
"""

import json
import re
from pathlib import Path
import subprocess
import sys
import tomllib

ROLES = ('master', 'volume', 'filer', 's3')
PORTS = dict(zip(ROLES, (9333, 8080, 8888, 8333)))
ROOT = '/etc/seaweedfs'
INBOUND = {
    'master': 'master-client,volume-client,filer-client,probe-client',
    'volume': 'master-client,filer-client,s3-client,probe-client',
    'filer': 'filer-client,s3-client,probe-client',
    's3': 'filer-client,probe-client',
}
OUTBOUND = {'master': 'master,volume', 'volume': 'master', 'filer': 'filer', 's3': 'filer'}


def security(role, signing_key=None):
    own = {
        'cert': f'{ROOT}/grpc.crt', 'key': f'{ROOT}/grpc.key',
        'client_cert': f'{ROOT}/client.crt', 'client_key': f'{ROOT}/client.key',
        'allowed_commonNames': INBOUND[role],
        'allowed_server_commonNames': OUTBOUND[role],
    }
    if role == 'filer':
        for target in ('master', 'volume', 's3'):
            own[f'{target}_allowed_server_commonNames'] = target
    result = {
        'tls': {'min_version': 'TLS 1.2'},
        'grpc': {'ca': f'{ROOT}/ca.crt', role: own,
                 'client': {'cert': f'{ROOT}/client.crt', 'key': f'{ROOT}/client.key',
                            'allowed_server_commonNames': OUTBOUND[role]}},
        'https': {'client': {'enabled': True, 'ca': f'{ROOT}/ca.crt',
                             'cert': f'{ROOT}/client.crt', 'key': f'{ROOT}/client.key',
                             'insecure_skip_verify': False}},
    }
    if role != 's3':
        result['https'][role] = {'cert': f'{ROOT}/http.crt', 'key': f'{ROOT}/http.key',
                                  'ca': f'{ROOT}/ca.crt'}
        if role == 'filer':
            result['https'][role]['disable_tls_verify_client_cert'] = False
    if signing_key is not None:
        result['jwt'] = {'filer_signing': {'key': signing_key, 'expires_after_seconds': 60}}
    return result


def arguments(role):
    common = [role, '-ip.bind=0.0.0.0']
    return common + {
        'master': ['-ip=master', '-mdir=/data'],
        'volume': ['-ip=volume', '-dir=/data', '-mserver=master:9333', '-max=10'],
        'filer': ['-ip=filer', '-master=master:9333', '-defaultStoreDir=/data', '-maxMB=1'],
        's3': ['-filer=filer:8888', f'-config={ROOT}/s3.json',
               f'-cert.file={ROOT}/http.crt', f'-key.file={ROOT}/http.key',
               f'-cacert.file={ROOT}/ca.crt', '-tlsVerifyClientCert=true',
               '-port.iceberg=0', '-port.lance=0'],
    }[role]


def render(config):
    lines = []
    def section(name, table):
        lines.append(f'[{name}]')
        for key, value in table.items():
            if not isinstance(value, dict):
                lines.append(f'{key} = {json.dumps(value)}')
        for key, value in table.items():
            if isinstance(value, dict):
                section(f'{name}.{key}', value)
    for name, table in config.items():
        section(name, table)
    return '\n'.join(lines) + '\n'


def openssl(*args):
    result = subprocess.run(['openssl', *map(str, args)], capture_output=True, check=False, timeout=10)
    if result.returncode:
        raise ValueError('invalid TLS material: ' + result.stderr.decode().splitlines()[-1])
    return result.stdout


def validate(directory, role, argv, environment):
    if role not in ROLES:
        raise ValueError('only separated roles are admitted')
    # Exact argv/env disallow duplicate flags, Go double-dash aliases, extra
    # listeners, alternate config search paths and WEED_ environment overrides.
    if argv != arguments(role) or environment != {}:
        raise ValueError('unexpected command or environment override')
    directory = Path(directory)
    parsed = tomllib.loads((directory / 'security.toml').read_text())
    signing_key = None
    if 'jwt' in parsed:
        jwt = parsed['jwt']
        if not isinstance(jwt, dict) or not isinstance(jwt.get('filer_signing'), dict):
            raise ValueError('invalid filer admin signing configuration')
        signing_key = jwt['filer_signing'].get('key', '')
        if role not in ('filer', 's3') or not isinstance(signing_key, str) or not re.fullmatch(r'[0-9a-f]{64}', signing_key):
            raise ValueError('invalid filer admin signing configuration')
    if parsed != security(role, signing_key):
        raise ValueError('TLS profile differs from the bounded role policy')
    expected = {'security.toml', 'ca.crt', 'grpc.crt', 'grpc.key', 'http.crt',
                'http.key', 'client.crt', 'client.key'}
    if role == 's3':
        expected.add('s3.json')
    if {p.name for p in directory.iterdir()} != expected:
        raise ValueError('missing material or another identity mounted')
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError('material must be regular files, not symlinks')
    ca = directory / 'ca.crt'
    for stem in ('grpc', 'http', 'client'):
        cert, key = directory / f'{stem}.crt', directory / f'{stem}.key'
        purpose = 'sslclient' if stem == 'client' else 'sslserver'
        if stem != 'client':
            san = openssl('x509', '-in', cert, '-noout', '-ext', 'subjectAltName').decode()
            if not san.strip() or f'DNS:{role}' not in {
                    item.strip() for item in san.splitlines()[-1].split(',')}:
                raise ValueError('explicit target DNS SAN is required; CN fallback is forbidden')
        options = [] if stem == 'client' else ['-verify_hostname', role]
        openssl('verify', '-CAfile', ca, '-purpose', purpose, *options, cert)
        cert_pub = openssl('x509', '-in', cert, '-pubkey', '-noout')
        key_pub = openssl('pkey', '-in', key, '-passin', 'pass:', '-pubout')
        if cert_pub != key_pub:
            raise ValueError('certificate/private-key mismatch')
        subject = openssl('x509', '-in', cert, '-subject', '-noout', '-nameopt', 'RFC2253')
        expected_cn = role + '-client' if stem == 'client' else role
        if subject.decode().strip() != 'subject=CN=' + expected_cn:
            raise ValueError('wrong role identity')


if __name__ == '__main__':
    try:
        directory, role, manifest = sys.argv[1:]
        config = json.loads(Path(manifest).read_text())
        validate(directory, role, config['argv'], config['environment'])
    except (ValueError, KeyError, OSError) as error:
        print(f'REFUSED: {error}', file=sys.stderr)
        sys.exit(78)
    print('Profile preflight passed; Phase A remains blocked by native gRPC identity policy.')
