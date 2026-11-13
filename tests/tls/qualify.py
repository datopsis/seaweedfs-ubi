"""Native image TLS qualification; run identically on amd64 and arm64.

Reports exact current behavior separately from Phase A acceptance. Private PKI,
S3 credentials and raw container logs never enter the report. Any unexpected
outcome fails the suite. Known native-policy gaps are BLOCKER rows, not passes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / 'scripts/lib'), str(REPO / 'tests/lib')]
from tls_profile import ROLES, PORTS, ROOT, arguments, render, security, validate
from s3client import S3Client
from pki import ca, leaf

RPC = {
    'master': '/master_pb.Seaweed/GetMasterConfiguration',
    'volume': '/volume_server_pb.VolumeServer/VolumeStatus',
    'filer': '/filer_pb.SeaweedFiler/GetFilerConfiguration',
    's3': '/messaging_pb.SeaweedS3IamCache/ListPolicies',
}
# A real other role, signed by the trusted CA but excluded from this listener.
SWAP = {'master': 's3', 'volume': 'volume', 'filer': 'master', 's3': 'master'}
TLS_ERROR = re.compile(r'certificate|unknown ca|bad certificate|tls.*alert|ssl.*alert', re.I)


def command(args, **kwargs):
    return subprocess.run(list(map(str, args)), capture_output=True, timeout=120, **kwargs)


class Qualification:
    def __init__(self, work, report):
        self.work, self.report = work, report
        self.runtime = os.environ.get('CONTAINER_RUNTIME', 'podman')
        self.image = os.environ.get('IMAGE', 'localhost/seaweedfs-ubi:development')
        self.prefix = 'tls-' + secrets.token_hex(5)
        self.network = self.prefix
        self.rows = []
        self.serial = 0
        self.pki = work / 'pki'
        self.pki.mkdir()
        self.names = {role: self.prefix + '-' + role for role in ROLES}
        self.ports = {}
        self.credentials = {'accessKey': secrets.token_hex(16), 'secretKey': secrets.token_hex(32)}

    def run(self, *args, check=True, **kwargs):
        result = command([self.runtime, *args], **kwargs)
        if check and result.returncode:
            # Runtime diagnostics may contain credentials; retain locally only.
            (self.work / 'runtime-error.txt').write_bytes(result.stderr)
            raise AssertionError(f'container command failed: {args[0]} (raw diagnostic kept locally)')
        return result

    def row(self, listener, case, expected, actual, detail=''):
        match = expected == actual
        status = 'PASS' if match else 'FAIL'
        if match and expected == 'ACCEPTED-BLOCKER':
            status = 'BLOCKER'
        self.rows.append(dict(listener=listener, case=case, expected=expected,
                              actual=actual, status=status, detail=detail))
        print(f'{status}: {listener} {case}: {actual} {detail}', flush=True)
        self.save()
        if not match:
            raise AssertionError(f'{listener}/{case}: expected {expected}, got {actual}')

    def save(self):
        self.report.write_text(json.dumps({
            'schema': 1, 'version': '4.53', 'architecture': platform.machine(),
            'commit': os.environ.get('SOURCE_COMMIT', command(['git', 'rev-parse', 'HEAD']).stdout.decode().strip()),
            'artifact_lock_sha256': hashlib.sha256((REPO / 'artifacts/seaweedfs.lock.json').read_bytes()).hexdigest(),
            'phase_a_complete': False, 'rows': self.rows,
            'limitations': ['one host, separated roles; no rotation or revocation qualification',
                            'OpenID/user authentication is Phase B',
                            'native outgoing S3 gRPC callback identity mutations not yet verified',
                            'TLS-only STS AssumeRole belongs to held PR #80; not verified here'],
        }, indent=2) + '\n')

    def prepare(self):
        ca(self.pki, 'ca')
        ca(self.pki, 'other-ca')
        for role in (*ROLES, 'probe'):
            leaf(self.pki, role + '-client', role + '-client', role + '-client', 'clientAuth')
        for role in ROLES:
            for variant, issuer, expired, cn, san in (
                ('valid', 'ca', False, role, role),
                ('wrong-san', 'ca', False, role, 'wrong.invalid'),
                ('wrong-ca', 'other-ca', False, role, role),
                ('expired', 'ca', True, role, role),
            ):
                leaf(self.pki, role + '-' + variant, cn, san, 'serverAuth', issuer, expired)
        leaf(self.pki, 'untrusted-client', 'probe-client', 'probe-client', 'clientAuth', 'other-ca')
        leaf(self.pki, 'expired-client', 'probe-client', 'probe-client', 'clientAuth', expired=True)
        for role in ROLES:
            cfg = self.work / role
            cfg.mkdir(mode=0o755)
            for protocol in ('http', 'grpc'):
                self.copy_leaf(role, protocol, role + '-valid')
            for ext in ('crt', 'key'):
                shutil.copyfile(self.pki / f'{role}-client.{ext}', cfg / f'client.{ext}')
            shutil.copyfile(self.pki / 'ca.crt', cfg / 'ca.crt')
            (cfg / 'security.toml').write_text(render(security(role)))
            if role == 's3':
                (cfg / 's3.json').write_text(json.dumps({'identities': [{
                    'name': 'tls-probe', 'credentials': [self.credentials],
                    'actions': ['Admin', 'Read', 'Write', 'List', 'Tagging']}]}))
            validate(cfg, role, arguments(role), {})
            # Only the container's UID/group can read private mounted files.
            for path in cfg.iterdir():
                path.chmod(0o640)
            # Rootless Podman maps host owner to container root; GID 0 is the
            # image's declared supplemental access boundary, never world access.
        self.run('network', 'create', self.network)
        for role in ROLES:
            if role != 's3':
                self.run('volume', 'create', self.names[role] + '-data')
        self.start_all()

    def copy_leaf(self, role, protocol, name):
        cfg = self.work / role
        cfg.mkdir(exist_ok=True)
        for ext in ('crt', 'key'):
            shutil.copyfile(self.pki / f'{name}.{ext}', cfg / f'{protocol}.{ext}')
            (cfg / f'{protocol}.{ext}').chmod(0o640)

    def start(self, role):
        self.run('rm', '-f', self.names[role], check=False)
        args = ['run', '-d', '--name', self.names[role], '--network', self.network,
                '--network-alias', role, '--read-only', '--cap-drop=ALL',
                '--security-opt=no-new-privileges',
                '-v', f'{self.work / role}:{ROOT}:ro']
        if role != 's3':
            args += ['-v', f'{self.names[role]}-data:/data']
        for port in (PORTS[role], PORTS[role] + 10000):
            args += ['-p', f'127.0.0.1::{port}']
        self.run(*args, self.image, *arguments(role))
        mapping = json.loads(self.run('inspect', self.names[role]).stdout)[0]['NetworkSettings']['Ports']
        for port in (PORTS[role], PORTS[role] + 10000):
            self.ports[role, port == PORTS[role] + 10000] = int(mapping[f'{port}/tcp'][0]['HostPort'])
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if self.socket_ports(role) == {PORTS[role], PORTS[role] + 10000}:
                return
            state = json.loads(self.run('inspect', self.names[role]).stdout)[0]['State']['Status']
            if state == 'exited':
                break
            time.sleep(0.25)
        self.logs()
        raise AssertionError(f'{role} did not start its exact listener set')

    def start_all(self):
        for role in reversed(ROLES):
            self.run('rm', '-f', self.names[role], check=False)
        for role in ROLES:
            self.start(role)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            result = self.curl('master', False, path='/readyz')
            if b'200 OK' in result.stdout:
                return
            time.sleep(0.25)
        raise AssertionError('master readiness deadline exceeded')

    def socket_ports(self, role):
        result = self.run('exec', self.names[role], 'cat', '/proc/net/tcp', '/proc/net/tcp6', check=False)
        ports = set()
        for line in result.stdout.decode().splitlines():
            fields = line.split()
            if len(fields) > 3 and fields[3] == '0A':
                ports.add(int(fields[1].split(':')[1], 16))
        return ports

    def logs(self):
        data = b''
        for role in ROLES:
            result = self.run('logs', self.names[role], check=False)
            combined = result.stdout + result.stderr
            (self.work / f'{role}.log').write_bytes(combined)
            data += combined
        return data.decode(errors='replace')

    def curl(self, role, grpc, client='probe-client', trust='ca', plaintext=False, path=None):
        port = self.ports[role, grpc]
        scheme = 'http' if plaintext else 'https'
        url = f'{scheme}://{role}:{port}' + (path or (RPC[role] if grpc else '/healthz'))
        args = ['curl', '--silent', '--show-error', '--noproxy', '*', '--max-time', '8',
                '--resolve', f'{role}:{port}:127.0.0.1', '--include']
        if not plaintext:
            args += ['--cacert', self.pki / f'{trust}.crt']
            if client:
                args += ['--cert', self.pki / f'{client}.crt', '--key', self.pki / f'{client}.key']
        if not grpc:
            args += ['--http1.1']
        if grpc:
            args += ['--http2-prior-knowledge' if plaintext else '--http2',
                     '-H', 'content-type: application/grpc', '-H', 'te: trailers',
                     '--data-binary', '@-']
        return command([*args, url], input=b'\0\0\0\0\0' if grpc else None)

    def positive(self, role, grpc):
        result = self.curl(role, grpc)
        if result.returncode or (grpc and b'grpc-status: 0' not in result.stdout.lower()) or (
                not grpc and b'200 OK' not in result.stdout):
            (self.work / 'probe-error.txt').write_bytes(result.stdout + result.stderr)
            raise AssertionError(f'valid {role}/{grpc} operation failed: curl={result.returncode}; '
                                 + result.stderr.decode(errors='replace'))

    def roundtrip(self):
        self.serial += 1
        # Resolve only the fixture name; TLS still verifies the real URL host.
        original = socket.getaddrinfo
        def resolve(host, *args, **kwargs):
            return original('127.0.0.1' if host == 's3' else host, *args, **kwargs)
        socket.getaddrinfo = resolve
        try:
            client = S3Client(f'https://s3:{self.ports["s3", False]}',
                              self.credentials['accessKey'], self.credentials['secretKey'],
                              ca_bundle=str(self.pki / 'ca.crt'))
            client.context.load_cert_chain(self.pki / 'probe-client.crt', self.pki / 'probe-client.key')
            bucket = f'tls-{self.serial}'
            payload = b'verified transport\n' * 131072
            assert client.create_bucket(bucket).status == 200
            assert client.put_object(bucket, 'object', payload).status == 200
            got = client.get_object(bucket, 'object')
            assert got.status == 200 and got.body == payload
            assert client.delete_object(bucket, 'object').status == 204
            assert client.get_object(bucket, 'object').status == 404
            assert client.delete_bucket(bucket).status == 204
        finally:
            socket.getaddrinfo = original

    def inventory(self):
        for role in ROLES:
            assert self.socket_ports(role) == {PORTS[role], PORTS[role] + 10000}
            status = self.run('exec', self.names[role], 'cat', '/proc/1/status').stdout.decode()
            assert re.search(r'Uid:\s+1000\s+1000\s+1000\s+1000', status)
            assert re.search(r'CapEff:\s+0+\n', status)
            assert re.search(r'NoNewPrivs:\s+1', status)
            assert self.run('exec', self.names[role], 'touch', '/root-write-probe', check=False).returncode
            # Each other role's private path is absent, even for the same UID.
            for other in ROLES:
                if other != role:
                    assert self.run('exec', self.names[role], 'cat', f'{ROOT}/{other}/client.key', check=False).returncode
            inspect = json.loads(self.run('inspect', self.names[role]).stdout)[0]
            mounts = [m for m in inspect['Mounts'] if m['Destination'] == ROOT]
            assert len(mounts) == 1 and not mounts[0]['RW']
            assert Path(mounts[0]['Source']) == self.work / role
            self.row(role, 'socket-inventory-and-runtime', 'RESTRICTED', 'RESTRICTED',
                     f'IPv4/IPv6 TCP inventory exactly {PORTS[role]},{PORTS[role]+10000}; own keys only')

    def negatives(self):
        for role in ROLES:
            for grpc in (False, True):
                listener = f'{role}/{"grpc" if grpc else "https"}'
                self.positive(role, grpc)
                for case, client, trust, plain in (
                    ('no-client-cert', None, 'ca', False),
                    ('wrong-client-ca', 'untrusted-client', 'ca', False),
                    ('expired-client', 'expired-client', 'ca', False),
                    ('wrong-trust-bundle', 'probe-client', 'other-ca', False),
                    ('plaintext', None, 'ca', True),
                    *([('disallowed-role', SWAP[role] + '-client', 'ca', False)] if grpc else []),
                ):
                    self.positive(role, grpc)
                    result = self.curl(role, grpc, client=client, trust=trust, plaintext=plain)
                    evidence = result.stderr.decode(errors='replace')
                    if plain:
                        # Go HTTPS emits exactly this protocol-error body; gRPC
                        # closes the connection. Neither may return application data.
                        accepted = b'grpc-status: 0' in result.stdout.lower() or b'200 OK' in result.stdout
                        refused = not accepted and (result.returncode in (52, 56) or
                                  b'Client sent an HTTP request to an HTTPS server.' in result.stdout)
                    else:
                        refused = result.returncode in (35, 56, 60) and bool(TLS_ERROR.search(evidence))
                    self.row(listener, case, 'REFUSED', 'REFUSED' if refused else 'UNEXPECTED',
                             f'curl={result.returncode}; ' + evidence.strip()[:250])
                    self.positive(role, grpc)
                self.roundtrip()

    def server_negatives(self):
        for role in ROLES:
            for grpc in (False, True):
                protocol = 'grpc' if grpc else 'http'
                for variant in ('wrong-san', 'wrong-ca', 'expired'):
                    self.positive(role, grpc)
                    self.copy_leaf(role, protocol, f'{role}-{variant}')
                    self.start(role)
                    result = self.curl(role, grpc)
                    error = result.stderr.decode(errors='replace')
                    # curl's code 60 means server certificate verification, not
                    # application authorization, timeouts or service availability.
                    self.row(f'{role}/{protocol}', 'server-' + variant, 'REFUSED',
                             'REFUSED' if result.returncode == 60 else 'UNEXPECTED', error.strip()[:250])
                    self.copy_leaf(role, protocol, role + '-valid')
                    self.start(role)
                    self.positive(role, grpc)
            self.roundtrip()

    def native_canaries(self):
        # Fresh processes prevent a cached gRPC session from masking a mutation.
        # Separate HTTPS leaves remain valid: an object success therefore
        # demonstrates the stock native gRPC client accepted the wrong SAN.
        for role in ('master', 'volume', 'filer'):
            self.roundtrip()
            self.copy_leaf(role, 'grpc', role + '-wrong-san')
            self.start_all()
            self.roundtrip()
            self.row(role + '/grpc', 'native-correct-cn-wrong-san',
                     'ACCEPTED-BLOCKER', 'ACCEPTED-BLOCKER',
                     'stock roles completed signed S3 write, byte-exact read, delete with wrong DNS SAN')
            self.copy_leaf(role, 'grpc', role + '-valid')
            self.start_all()
            self.roundtrip()

    def cleanup(self):
        self.logs()
        for role in reversed(ROLES):
            self.run('rm', '-f', self.names[role], check=False)
            if role != 's3':
                self.run('volume', 'rm', '-f', self.names[role] + '-data', check=False)
        self.run('network', 'rm', self.network, check=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='seaweed-tls-') as directory:
        work = Path(directory)
        work.chmod(0o755)
        suite = Qualification(work, args.report)
        try:
            suite.prepare()
            suite.inventory()
            suite.roundtrip()
            suite.row('cluster', 'write-read-delete', 'SUCCEEDED', 'SUCCEEDED')
            suite.negatives()
            suite.server_negatives()
            suite.native_canaries()
        except Exception as error:
            suite.rows.append({'status': 'FAIL', 'detail': str(error)})
            print(f'FAIL: {error}', flush=True)
            raise
        finally:
            suite.save()
            suite.cleanup()


if __name__ == '__main__':
    main()
