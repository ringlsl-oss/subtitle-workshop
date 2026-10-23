"""Verify real packaged server, recognition subprocess and encoded output."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:18748'

with tempfile.TemporaryDirectory() as folder:
    with (ROOT / 'output' / 'packaged.log').open('w', encoding='utf-8') as log:
        executable = Path(os.environ.get('SUBTITLE_TEST_EXE', str(ROOT / 'dist' / '字幕工坊' / '字幕工坊.exe')))
        process = subprocess.Popen([str(executable), '--browser', '--port', '18748'], cwd=ROOT, env={**os.environ,'SUBTITLE_DATA_DIR':folder}, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    html = urlopen(BASE,timeout=2).read().decode()
                    break
                except Exception:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(.2)
            token = re.search(r'name="app-token" content="([^"]+)"', html)[1]
            def api(path, data=None):
                request = Request(BASE+'/api/'+path, data=json.dumps(data).encode() if data is not None else None, headers={'X-App-Token':token,'Content-Type':'application/json'})
                return json.load(urlopen(request,timeout=30))
            def wait(identifier):
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    job = api('jobs/'+identifier)['job']
                    if job['state'] not in ('running','cancelling'):
                        assert job['state'] == 'done', job
                        return job['result']
                    time.sleep(.25)
                raise AssertionError('job timeout')
            converted = api('simplify', {'cues': [{'start': 0, 'end': 2, 'text': '戰略之助動力電池\nAI 技術'}]})
            assert converted['cues'] == [{'start': 0, 'end': 2, 'text': '战略之助动力电池\nAI 技术'}]
            media = api('media',{'path':str(ROOT/'output'/'test-video.mp4')})['media']
            document_path = Path(folder) / 'script.txt'
            document_path.write_text('Hello welcome to the Subtitle Studio. We can edit subtitles and remember your personal style.', encoding='utf-8')
            document = api('import-document', {'path': str(document_path)})['document']
            job = api('jobs',{'kind':'transcribe','path':media['path'],'model':'tiny','language':'en','reference_document':document})['job']
            recognized = wait(job['id'])
            assert recognized['application']['profile_id'] == 'default'
            cues = recognized['cues']
            assert recognized['comparison']['rows'], recognized
            assert recognized['comparison']['source_cues'] == cues
            assert any('Workshop' in c['text'] for c in cues), 'Reference must not silently replace speech'
            assert api('compare-document', {'cues':cues, 'document':document})['comparison']['rows']
            assert 'welcome' in ' '.join(c['text'].lower() for c in cues)
            project = api('state')['project']
            project['media'],project['cues'] = media,cues
            api('project',project)
            output = ROOT/'output'/'packaged-export.mp4'
            job = api('jobs',{'kind':'burn','project':project,'path':str(output)})['job']
            wait(job['id'])
            metadata = api('media',{'path':str(output)})['media']
            assert (metadata['width'],metadata['height']) == (1280,720),metadata
            assert output.stat().st_size > 10000
            saved = api('outputs')['outputs']
            assert saved[0]['format'] == 'mp4'
            assert 'url' in api('output-preview', {'id':saved[0]['id']})['media']
            print('PACKAGED_SMOKE_OK: OpenCC, document import, independent recognition and comparison, media probe, autosave, real MP4 export')
        finally:
            process.terminate()
            process.wait(timeout=10)
