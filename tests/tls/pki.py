"""Ephemeral test PKI, never uploaded. OpenSSL is already a CI prerequisite."""
from pathlib import Path
import subprocess


def ssl(*args):
    subprocess.run(['openssl', *map(str, args)], check=True, capture_output=True)


def ca(root, name):
    ssl('req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
        '-nodes', '-days', '1', '-subj', f'/CN={name}',
        '-keyout', root / f'{name}.key', '-out', root / f'{name}.crt')


def leaf(root, name, cn, san, purpose, issuer='ca', expired=False):
    root = Path(root)
    ssl('req', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256', '-nodes',
        '-subj', f'/CN={cn}', '-keyout', root / f'{name}.key', '-out', root / f'{name}.csr')
    ext = root / f'{name}.ext'
    ext.write_text(f'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n'
                   f'extendedKeyUsage={purpose}\nsubjectAltName=DNS:{san}\n')
    if expired:
        (root / 'index').write_text('')
        (root / 'serial').write_text('1000\n')
        config = root / 'ca.conf'
        config.write_text(f'[ca]\ndefault_ca=local\n[local]\ndatabase={root}/index\n'
                          f'serial={root}/serial\nnew_certs_dir={root}\n'
                          f'certificate={root}/{issuer}.crt\nprivate_key={root}/{issuer}.key\n'
                          'default_md=sha256\npolicy=policy\n[policy]\ncommonName=supplied\n')
        ssl('ca', '-batch', '-notext', '-config', config, '-extfile', ext,
            '-startdate', '20200101000000Z', '-enddate', '20200102000000Z',
            '-in', root / f'{name}.csr', '-out', root / f'{name}.crt')
    else:
        ssl('x509', '-req', '-days', '1', '-in', root / f'{name}.csr',
            '-CA', root / f'{issuer}.crt', '-CAkey', root / f'{issuer}.key',
            '-CAcreateserial', '-extfile', ext, '-out', root / f'{name}.crt')
