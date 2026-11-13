"""Query the enabled repositories extracted from the digest-pinned UBI base.

The image inherits its RPMs; assembly installs none and removes repo files.
Never substitute the runner's repositories or a separate hand-maintained list.
"""
import configparser
import hashlib
from pathlib import Path

RPM_ARCH = {'amd64': 'x86_64', 'arm64': 'aarch64'}


def repositories(arch, directory):
    paths = sorted(Path(directory).glob('*.repo'))
    if not paths:
        raise ValueError('missing base-image repository configuration')
    config = configparser.ConfigParser(interpolation=None)
    digest = hashlib.sha256()
    for path in paths:
        data = path.read_bytes()
        digest.update(path.name.encode() + b'\0' + data)
        config.read_string(data.decode(), source=str(path))
    if config.defaults():
        raise ValueError('unexpected repository defaults')
    urls = {}
    expected = {f'ubi-9-{name}-rpms': name for name in ('baseos', 'appstream', 'codeready-builder')}
    for name in config.sections():
        entry = config[name]
        if not entry.getboolean('enabled'):
            continue
        if name not in expected or entry.getboolean('gpgcheck') is not True:
            raise ValueError('unexpected or unsigned enabled repository')
        if set(entry) - {'name', 'baseurl', 'enabled', 'gpgkey', 'gpgcheck'}:
            raise ValueError('unsupported repository options; refusing to ignore build configuration')
        url = entry['baseurl'].replace('$basearch', RPM_ARCH[arch])
        if url.rstrip('/') != f'https://cdn-ubi.redhat.com/content/public/ubi/dist/ubi9/9/{RPM_ARCH[arch]}/{expected[name]}/os':
            raise ValueError('unexpected UBI repository URL')
        urls[name] = url
    if set(urls) != set(expected):
        raise ValueError('missing enabled UBI repositories')
    return {'config_sha256': digest.hexdigest(), 'urls': urls}


def configure(base, tmp, arch, directory):
    import dnf.repo

    evidence = repositories(arch, directory)
    for name in ['root', 'cache', 'persist']:
        Path(tmp, name).mkdir()
    base.conf.installroot = tmp + '/root'
    base.conf.cachedir = tmp + '/cache'
    base.conf.logdir = tmp
    base.conf.persistdir = tmp + '/persist'
    base.conf.reposdir = []
    base.conf.install_weak_deps = False
    base.conf.arch = RPM_ARCH[arch]
    base.conf.ignorearch = True
    base.conf.substitutions.update(arch=RPM_ARCH[arch], basearch=RPM_ARCH[arch], releasever='9')
    base.conf.module_platform_id = 'platform:el9'
    for name, url in evidence['urls'].items():
        repo = dnf.repo.Repo(name, base.conf)
        repo.baseurl = [url]
        repo.gpgcheck = True
        repo.skip_if_unavailable = False
        repo.metadata_expire = 0
        repo.timeout = 30
        repo.retries = 1
        base.repos.add(repo)
    base.fill_sack(load_system_repo=False)
    for name in evidence['urls']:
        if not base.sack.query().available().filter(reponame=name):
            raise ValueError(f'missing or empty UBI repository: {name}')
    return evidence
