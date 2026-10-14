"""Prepare a minimal Cloud Run source deployment without a Dockerfile."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def prepare(destination):
    destination = Path(destination).resolve()
    if destination.is_relative_to(ROOT):
        raise ValueError('Choose a new directory outside this repository.')
    if destination.exists():
        raise FileExistsError('Destination already exists; choose a new directory.')
    manifest = json.loads((ROOT / 'build_manifest.json').read_text())
    dist = ROOT / 'dist'
    files = {'index.html': manifest['sha256']}
    files.update({name: value['sha256'] for name, value in manifest['files'].items()})
    files[manifest['standalone']['file']] = manifest['standalone']['sha256']
    for name, expected in files.items():
        source = (dist / name).resolve()
        if not source.is_relative_to(dist.resolve()):
            raise ValueError('Invalid manifest path.')
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Build mismatch: {name}; rebuild and validate first.')
    if hashlib.sha256(gzip.decompress((dist / 'index.html.gz').read_bytes())).hexdigest() != manifest['sha256']:
        raise ValueError('Compressed index does not match the build.')
    destination.mkdir(parents=True)
    for name in [*files, 'index.html.gz']:
        target = destination / 'dist' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dist / name, target)
    shutil.copy2(ROOT / 'serve.py', destination / 'serve.py')
    runtime_files = ['requirements.txt', 'Procfile', '.python-version']
    for name in runtime_files:
        shutil.copy2(ROOT / 'deploy' / 'cloudrun' / name, destination / name)
    (destination / '.gcloudignore').write_text(
        '**\n!serve.py\n!requirements.txt\n!Procfile\n!.python-version\n!dist/\n!dist/**\n',
        encoding='utf-8',
    )
    print(f'Prepared {len(files) + 5} runtime files in {destination}')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    prepare(parser.parse_args().directory)
