"""Assemble the shareable bundle from reviewed app build and installed wheels.

Run with the Python that owns openai-whisper. Never copy user application data.
"""
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'output' / 'portable-staging' / '字幕工坊-1.0.3'
DOWNLOADS = ROOT / 'output' / 'portable-downloads'


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'output' / 'portable-app' / '字幕工坊', DEST, dirs_exist_ok=True)
    internal = DEST / '_internal'
    python = internal / 'runtime' / 'python'
    python.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(DOWNLOADS / 'python-embed.zip') as archive:
        archive.extractall(python)
    (python / 'python312._pth').write_text('python312.zip\n.\nLib/site-packages\n# import site\n', encoding='utf-8')
    site = python / 'Lib' / 'site-packages'
    site.mkdir(parents=True, exist_ok=True)
    queue, copied, manifest = ['openai-whisper'], set(), []
    while queue:
        name = canonicalize_name(queue.pop())
        if name in copied:
            continue
        dist = metadata.distribution(name)
        for requirement in dist.requires or []:
            req = Requirement(requirement)
            if req.marker is None or req.marker.evaluate({'extra': ''}):
                assert metadata.version(req.name) in req.specifier, requirement
                queue.append(req.name)
        count = 0
        for item in dist.files or []:
            relative = Path(str(item))
            if '..' in relative.parts or relative.suffix == '.pyc' or '__pycache__' in relative.parts:
                continue
            source = Path(dist.locate_file(item))
            if not source.is_file():
                continue
            target = site / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            count += 1
        manifest.append({'name': name, 'version': dist.version, 'files': count})
        copied.add(name)
        print(name, dist.version, count, flush=True)
    # App-local C/C++ runtime for PyTorch on computers without a VC installer.
    system = Path(os.environ['SystemRoot']) / 'System32'
    for pattern in ('msvcp140*.dll', 'vcruntime140*.dll', 'concrt140.dll'):
        for source in system.glob(pattern):
            shutil.copy2(source, python / source.name)
    models = internal / 'models'
    models.mkdir(exist_ok=True)
    import whisper
    for name in ('tiny', 'small'):
        source = Path.home() / '.cache' / 'whisper' / (name + '.pt')
        digest = hashlib.file_digest(source.open('rb'), 'sha256').hexdigest()
        assert digest == whisper._MODELS[name].split('/')[-2], 'Model checksum mismatch'
        shutil.copy2(source, models / source.name)
        print('model', name, digest, flush=True)
    unpacked = DOWNLOADS / 'webview2-unpacked'
    unpacked.mkdir(exist_ok=True)
    with (DOWNLOADS / 'webview2-expand.log').open('w') as log:
        subprocess.run([str(system / 'expand.exe'), str(DOWNLOADS / 'webview2-x64.cab'), '-F:*', str(unpacked)], check=True, stdout=log, stderr=log)
    browser = next(unpacked.rglob('msedgewebview2.exe')).parent
    shutil.copytree(browser, internal / 'webview2', dirs_exist_ok=True)
    (internal / 'runtime.json').write_text(json.dumps({'python': 'runtime/python/python.exe', 'site_packages': [], 'models': 'models'}, indent=2), encoding='utf-8')
    (DEST / 'portable.flag').write_text('Local data lives next to this flag in data/.\n', encoding='utf-8')
    (DEST / '组件清单.json').write_text(json.dumps({'python': '3.12.10 embedded x64', 'webview2': browser.name, 'recognition': manifest, 'models': ['tiny', 'small']}, indent=2, ensure_ascii=False), encoding='utf-8')
    assert not (DEST / 'data').exists(), 'Do not include personal data in a shareable build'
    print('ASSEMBLED', DEST, flush=True)


if __name__ == '__main__':
    main()
