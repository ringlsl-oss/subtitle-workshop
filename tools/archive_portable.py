import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'output' / 'portable-staging' / '字幕工坊-1.0.3'
output = ROOT / '分享包'
output.mkdir(exist_ok=True)
archive = output / '字幕工坊-1.0.3-Windows-x64-免安装.zip'
assert not (source / 'data').exists(), 'Never package personal data'
settings = json.loads((source / '_internal' / 'runtime.json').read_text(encoding='utf-8'))
assert not Path(settings['python']).is_absolute()
assert settings['site_packages'] == []
paths = sorted(p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as package:
    for index, path in enumerate(paths):
        package.write(path, str(Path(source.name) / path.relative_to(source)), compress_type=zipfile.ZIP_STORED if path.suffix == '.pt' else zipfile.ZIP_DEFLATED)
        if index % 1000 == 0:
            print('ZIP_PROGRESS', index, '/', len(paths), flush=True)
with zipfile.ZipFile(archive) as package:
    assert package.testzip() is None, 'Archive CRC validation failed'
    names = package.namelist()
    assert not any(n.startswith(source.name + '/data/') for n in names)
    assert not any(n.endswith(('.zmproj', 'profiles.json', 'autosave.json')) for n in names)
with archive.open('rb') as file:
    digest = hashlib.file_digest(file, 'sha256').hexdigest()
archive.with_suffix('.zip.sha256.txt').write_text(digest + '  ' + archive.name + '\n', encoding='utf-8')
print('ARCHIVE_OK', archive, 'BYTES', archive.stat().st_size, 'SHA256', digest, flush=True)
