"""Profile preflight must reject unsafe rendered configuration before launch."""
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'scripts/lib'), str(REPO / 'tests/tls')]
from tls_profile import arguments, render, security, validate
from pki import ca, leaf, ssl


class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        ca(cls.root, 'ca')
        leaf(cls.root, 'server', 'filer', 'filer', 'serverAuth')
        leaf(cls.root, 'client', 'filer-client', 'filer-client', 'clientAuth')
        cls.base = cls.root / 'base'
        cls.base.mkdir()
        for stem in ('http', 'grpc'):
            for ext in ('crt', 'key'):
                shutil.copyfile(cls.root / f'server.{ext}', cls.base / f'{stem}.{ext}')
        for name in ('ca.crt', 'client.crt', 'client.key'):
            shutil.copyfile(cls.root / name, cls.base / name)
        (cls.base / 'security.toml').write_text(render(security('filer')))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.cfg = self.root / 'case'
        if self.cfg.exists():
            shutil.rmtree(self.cfg)
        shutil.copytree(self.base, self.cfg)

    def check(self, argv=None, env=None):
        validate(self.cfg, 'filer', arguments('filer') if argv is None else argv,
                 {} if env is None else env)

    def test_valid(self):
        self.check()

    def test_missing_and_malformed_material(self):
        for name in ('ca.crt', 'http.crt', 'http.key', 'grpc.crt', 'grpc.key',
                     'client.crt', 'client.key', 'security.toml'):
            for operation in ('remove', 'corrupt'):
                with self.subTest(name=name, operation=operation):
                    self.setUp()
                    path = self.cfg / name
                    path.unlink() if operation == 'remove' else path.write_text('malformed')
                    with self.assertRaises((ValueError, OSError)):
                        self.check()

    def test_missing_sections_and_verification_downgrades(self):
        cases = []
        for section in ('grpc', 'https', 'tls'):
            config = security('filer')
            del config[section]
            cases.append(config)
        for section, key, value in (
            ('client', 'enabled', False), ('client', 'insecure_skip_verify', True),
            ('filer', 'disable_tls_verify_client_cert', True),
        ):
            config = security('filer')
            config['https'][section][key] = value
            cases.append(config)
        for field in ('allowed_commonNames', 'allowed_server_commonNames',
                      'master_allowed_server_commonNames', 'volume_allowed_server_commonNames',
                      's3_allowed_server_commonNames'):
            config = security('filer')
            config['grpc']['filer'][field] = '*'
            cases.append(config)
        for config in cases:
            with self.subTest(config=config):
                (self.cfg / 'security.toml').write_text(render(config))
                with self.assertRaises(ValueError):
                    self.check()

    def test_flags_environment_and_config_search_overrides(self):
        for flag in ('--port.https=8443', '-metricsPort=9000', '-debug=true',
                     '-s3', '-ip=filer-alias', '-port=8081'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                self.check(argv=arguments('filer') + [flag])
        for name in ('WEED_HTTPS_CLIENT_ENABLED', 'WEED_GRPC_CA',
                     'SEAWEEDFS_UBI_ALLOW_PLAINTEXT_BESIDE_TLS', 'HOME'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.check(env={name: 'unexpected'})

    def test_foreign_key_and_symlink_refused(self):
        (self.cfg / 'master.key').write_text('foreign')
        with self.assertRaises(ValueError):
            self.check()
        (self.cfg / 'master.key').unlink()
        (self.cfg / 'client.key').unlink()
        (self.cfg / 'client.key').symlink_to(self.root / 'client.key')
        with self.assertRaises(ValueError):
            self.check()

    def test_mismatched_key(self):
        shutil.copyfile(self.cfg / 'client.key', self.cfg / 'grpc.key')
        with self.assertRaises(ValueError):
            self.check()

    def test_cn_only_server_certificate_refused(self):
        # OpenSSL verify_hostname alone falls back to CN if SAN is absent.
        ssl('x509', '-req', '-days', '1', '-in', self.root / 'server.csr',
            '-CA', self.root / 'ca.crt', '-CAkey', self.root / 'ca.key',
            '-CAcreateserial', '-out', self.cfg / 'grpc.crt')
        with self.assertRaisesRegex(ValueError, 'explicit target DNS SAN'):
            self.check()

    def test_wrong_san_expired_and_wrong_role_refused(self):
        for name, cn, san, expired in (
            ('wrong-san', 'filer', 'wrong.invalid', False),
            ('expired', 'filer', 'filer', True),
            ('role-swap', 'master', 'master', False),
        ):
            with self.subTest(name=name):
                leaf(self.root, name, cn, san, 'serverAuth', expired=expired)
                for ext in ('crt', 'key'):
                    shutil.copyfile(self.root / f'{name}.{ext}', self.cfg / f'grpc.{ext}')
                with self.assertRaises(ValueError):
                    self.check()

    def test_no_verification_bypass_in_phase_a_execution(self):
        # Narrow scope: the Phase A executable harness. Historical tests are
        # independent evidence and never used to satisfy a Phase A assertion.
        code = (REPO / 'tests/tls/qualify.py').read_text()
        patterns = (
            r'--insecure|[\"\']-k[\"\']',
            r'check_hostname\s*=\s*false|cert_none|_create_unverified_context',
            r'verify\s*=\s*false|insecure_?skip_?verify\s*[:=]\s*true',
            r'danger_accept_invalid_(?:certs|hostnames)',
            r'aws_allow_(?:invalid_certificates|http)\s*=\s*true',
            r'(?:proxy|grpc)_ssl_verify\s+off',
            r'sslmode\s*=\s*(?:require|allow|prefer|disable|verify-ca)',
        )
        for pattern in patterns:
            self.assertIsNone(re.search(pattern, code, re.I), pattern)
        self.assertNotIn('\r', code)


if __name__ == '__main__':
    unittest.main()
