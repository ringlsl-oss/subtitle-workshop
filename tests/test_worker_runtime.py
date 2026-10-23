"""Recognition must work outside the developer app's virtualized user site."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_worker_loads_configured_dependencies_without_automatic_user_site(tmp_path):
    root = Path(__file__).resolve().parents[1]
    shutil.copy2(root / 'transcribe_worker.py', tmp_path)
    packages = tmp_path / '实际依赖目录'
    packages.mkdir()
    (packages / 'torch.py').write_text('def set_num_threads(count): pass\n', encoding='utf-8')
    (packages / 'whisper.py').write_text('''
import os
from pathlib import Path
class Model:
    def transcribe(self, *args, **kwargs):
        assert Path(os.environ['PATH'].split(os.pathsep)[0]) == Path(__file__).parent.parent / 'bin'
        return {'segments': [{'start': 0, 'end': 1, 'text': '识别成功'}]}
def load_model(*args, **kwargs): return Model()
''', encoding='utf-8')
    (tmp_path / 'bin').mkdir()
    (tmp_path / 'bin' / 'ffmpeg.exe').touch()
    (tmp_path / 'runtime.json').write_text(json.dumps({'site_packages': [str(packages)]}), encoding='utf-8')
    request = tmp_path / 'request.json'
    request.write_text(json.dumps({'path': 'fixture.wav', 'model': 'tiny'}), encoding='utf-8')
    output = tmp_path / 'result.json'
    result = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(tmp_path / 'transcribe_worker.py'), str(request), str(output)], capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding='utf-8'))[0]['text'] == '识别成功'
