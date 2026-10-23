"""Run inside the embedded Python, with network and user packages unavailable."""
import json
from pathlib import Path
import runpy
import socket
import sys

worker, audio, folder = map(Path, sys.argv[1:4])
bundle = worker.parent
assert all(Path(p).is_relative_to(bundle) for p in sys.path), sys.path


def offline(*args, **kwargs):
    raise AssertionError('Portable recognition attempted a network connection')


socket.socket.connect = offline
socket.create_connection = offline
folder.mkdir(parents=True, exist_ok=True)
request, output = folder / 'request.json', folder / 'result.json'
request.write_text(json.dumps({'path': str(audio), 'model': 'small', 'language': 'zh'}), encoding='utf-8')
sys.argv = [str(worker), str(request), str(output)]
runpy.run_path(str(worker), run_name='__main__')
result = json.loads(output.read_text(encoding='utf-8'))
assert result and '字幕' in ''.join(c['text'] for c in result), result
print('PORTABLE_OFFLINE_SMALL_OK ' + json.dumps(result, ensure_ascii=True))
