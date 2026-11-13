"""Run with /usr/bin/python3: exercise real librpm comparison and mocked DNF."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests' / 'lib'))
from ubi_repoquery import at_least, evr, query
from ubi_repos import repositories


class RpmTests(unittest.TestCase):
    def test_epoch_version_release_ordering(self):
        for candidate, fixed, expected in [
            ('2.37.4-28.el9_9', '2.37.4-28.el9_9', True),
            ('2.37.4-28.el9_9.1', '2.37.4-28.el9_9', True),
            ('2.37.4-28.el9_9', '2.37.4-28.el9_9.1', False),
            ('2.37.4-25.el9', '2.37.4-28.el9_9', False),
            ('1:1.0-1', '0:9.0-99', True), ('0:9.0-99', '1:1.0-1', False),
            ('1.0-2', '0:1.0-2', True), ('1.0-10', '1.0-9', True),
            ('1.0~rc1-1', '1.0-1', False), ('1.0^git1-1', '1.0-1', True),
        ]:
            with self.subTest(candidate=candidate, fixed=fixed):
                self.assertEqual(at_least(candidate, fixed), expected)

    def test_unparsable_versions(self):
        for value in ['', 'unspecified', '1.0', '>=1.0-1', '1:2:1.0-1', '1.0-1,1.0-2',
                      '-1', '1.0-', ' 1.0-1', None, 1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                evr(value)

    def test_dnf_query_filters_arch_and_uses_any_fix_branch(self):
        base = Mock()
        filtered = base.sack.query.return_value.available.return_value.filter
        filtered.return_value = [SimpleNamespace(epoch=0, version='1.0', release='2')]
        result = query(base, {'name': 'sample', 'fixes': ['1.0-3', '1.0-2']}, 'arm64')
        self.assertTrue(result['available'])
        filtered.assert_called_once_with(name='sample', arch=['aarch64', 'noarch'])
        self.assertFalse(query(base, {'name': 'sample', 'fixes': ['1.0-3']}, 'arm64')['available'])
        filtered.return_value = []
        self.assertFalse(query(base, {'name': 'sample', 'fixes': ['1.0-2']}, 'arm64')['available'])
        with self.assertRaises(ValueError):
            query(base, {'name': 'sample', 'fixes': ['1.0-2', 'invalid']}, 'arm64')

    def test_missing_disabled_or_modified_repositories_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with self.assertRaises(ValueError):
                repositories('amd64', directory)
            path = directory / 'ubi.repo'
            source = ''.join(
                f'[ubi-9-{name}-rpms]\nenabled=1\ngpgcheck=1\n'
                f'baseurl=https://cdn-ubi.redhat.com/content/public/ubi/dist/ubi9/9/$basearch/{name}/os\n'
                for name in ('baseos', 'appstream', 'codeready-builder'))
            path.write_text(source)
            for arch, machine in [('amd64', 'x86_64'), ('arm64', 'aarch64')]:
                self.assertTrue(all(machine in url for url in repositories(arch, directory)['urls'].values()))
            for broken in [source.replace('enabled=1', 'enabled=0', 1),
                           source.replace('gpgcheck=1', 'gpgcheck=0', 1),
                           source.replace('https:', 'http:', 1),
                           source + 'exclude=sample\n']:
                path.write_text(broken)
                with self.assertRaises(ValueError):
                    repositories('amd64', directory)


if __name__ == '__main__':
    unittest.main()
