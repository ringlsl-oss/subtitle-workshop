"""Check a running desktop app's worker; never save or replace its project."""
import argparse
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--audio', type=Path, required=True)
parser.add_argument('--model', default='tiny')
parser.add_argument('--language', default='en')
args = parser.parse_args()
base = f'http://127.0.0.1:{args.port}'
token = re.search(r'name="app-token" content="([^"]+)"', urlopen(base).read().decode())[1]


def api(path, data=None):
    request = Request(base + '/api/' + path, data=json.dumps(data).encode() if data else None,
                      headers={'X-App-Token': token, 'Content-Type': 'application/json'})
    return json.load(urlopen(request, timeout=30))


job = api('jobs', {'kind': 'transcribe', 'path': str(args.audio.resolve()),
                   'model': args.model, 'language': args.language})['job']
deadline = time.monotonic() + 180
while time.monotonic() < deadline:
    job = api('jobs/' + job['id'])['job']
    if job['state'] not in ('running', 'cancelling'):
        break
    time.sleep(.5)
assert job['state'] == 'done', job
assert job['result']['cues'], job
print('LIVE_DESKTOP_RECOGNITION_OK ' + json.dumps(job['result'], ensure_ascii=True))
