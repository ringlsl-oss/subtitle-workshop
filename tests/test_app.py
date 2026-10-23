import json
import tempfile
import time
import unittest
from pathlib import Path
import app
import io
import subprocess
from unittest.mock import patch


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = app.create_app(Path(self.temp.name))
        self.client = self.app.test_client()
        self.headers = {'X-App-Token': self.app.config['APP_TOKEN']}

    def tearDown(self):
        self.temp.cleanup()

    def post(self, path, data):
        return self.client.post('/api/' + path, json=data, headers=self.headers)

    def test_mutations_require_session_token(self):
        self.assertEqual(self.client.post('/api/project', json={}).status_code, 403)

    def test_learning_report_distinguishes_added_duplicate_and_failed_files(self):
        source = Path(self.temp.name) / 'sample.srt'
        source.write_text('1\n00:00:00,000 --> 00:00:01,000\n我们出发\n', encoding='utf-8')
        result = self.post('learn', {'profile_id':'default', 'paths':[str(source), str(source), str(source.with_name('missing.srt'))]}).get_json()
        self.assertEqual(result['report']['added'], 1)
        self.assertEqual(result['report']['duplicates'], 1)
        self.assertEqual(result['report']['failed'], 1)
        state = self.client.get('/api/state', headers=self.headers).get_json()
        self.assertEqual(state['profiles'][0]['last_learning']['added'], 1)

    def test_segmentation_reports_the_exact_selected_rules(self):
        p = self.post('profile', {'name':'短句'}).get_json()['profile']
        p['rules'].update(target_chars=3, max_chars=4, max_lines=1)
        self.post('profile', p)
        result = self.post('resegment', {'profile_id':p['id'], 'cues':[{'start':0,'end':5,'text':'今天我们一起去看看外面的世界'}]}).get_json()
        self.assertEqual(result['application']['profile_id'], p['id'])
        self.assertEqual(result['application']['sample_count'], 0)
        self.assertEqual(result['application']['rules']['max_chars'], 4)
        self.assertTrue(all(len(c['text']) <= 4 for c in result['cues']))

    def test_recognition_uses_profile_snapshot_instead_of_later_rule_edits(self):
        p = self.post('profile', {'name':'选中的短句'}).get_json()['profile']
        p['rules'].update(target_chars=3, max_chars=4, max_lines=1)
        self.post('profile', p)
        media = Path(self.temp.name)/'source.wav'
        media.write_bytes(b'fixture')
        # Capture the job boundary without loading an actual speech model.
        with patch.object(self.app.config['JOBS'], 'start', return_value={'id':'queued'}) as launch:
            response = self.post('jobs', {'kind':'transcribe','path':str(media),'model':'tiny','profile_id':p['id']})
            self.assertEqual(response.status_code,200)
            captured = launch.call_args.args[1]
        p['rules']['max_chars']=20
        self.post('profile',p)
        root = Path(self.temp.name)
        raw = [{'start':0,'end':8,'text':'今天我们一起去看看外面的世界'}]
        (root/'transcribe_worker.py').write_text("import sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_text("+repr(json.dumps(raw))+",encoding='utf-8')",encoding='utf-8')
        job={'id':'snapshot','kind':'transcribe','state':'running'}
        with patch.object(app,'ROOT',root):
            self.app.config['JOBS'].run(job,captured)
        self.assertEqual(job['state'],'done',job.get('message'))
        self.assertEqual(job['result']['application']['profile_id'],p['id'])
        self.assertEqual(job['result']['application']['rules']['max_chars'],4)
        self.assertTrue(all(len(c['text'])<=4 for c in job['result']['cues']))

    def test_saved_outputs_survive_restart_and_failed_exports_not_recorded(self):
        project = self.client.get('/api/state', headers=self.headers).get_json()['project']
        project['cues']=[{'start':0,'end':1,'text':'成稿'}]
        target = Path(self.temp.name)/'成稿.srt'
        self.assertEqual(self.post('export-text', {'project':project,'path':str(target),'format':'srt'}).status_code,200)
        restarted = app.create_app(Path(self.temp.name))
        state = restarted.test_client().get('/api/state',headers={'X-App-Token':restarted.config['APP_TOKEN']}).get_json()
        self.assertEqual(state['outputs'][0]['path'],str(target.resolve()))
        self.assertEqual(state['outputs'][0]['format'],'srt')
        self.assertIn('saved_at',state['outputs'][0])
        preview=self.post('output-preview',{'id':state['outputs'][0]['id']}).get_json()
        self.assertIn('成稿',preview['text'])
        self.assertEqual(self.post('export-text', {'project':project,'path':str(target),'format':'unsupported'}).status_code,400)
        self.assertEqual(len(self.client.get('/api/outputs',headers=self.headers).get_json()['outputs']),1)

    def test_simplify_endpoint_converts_existing_subtitles_without_resegmenting(self):
        cues = [{'start': 10, 'end': 13, 'text': '動力電池\n語音識別'}]
        response = self.post('simplify', {'cues': cues})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['cues'], [{'start': 10, 'end': 13, 'text': '动力电池\n语音识别'}])

    def test_recognition_job_returns_simplified_text(self):
        # Replace only expensive model inference with a deterministic subprocess;
        # exercise the actual result loading and normalization in Jobs.run.
        root = Path(self.temp.name)
        raw = [{'start': 0, 'end': 2, 'text': '戰略之助動力電池'}]
        worker = "import sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_text(" + repr(json.dumps(raw)) + ", encoding='utf-8')\n"
        (root / 'transcribe_worker.py').write_text(worker, encoding='utf-8')
        job = {'id': 'recognition-test', 'kind': 'transcribe', 'state': 'running'}
        with patch.object(app, 'ROOT', root):
            self.app.config['JOBS'].run(job, {})
        self.assertEqual(job['state'], 'done', job.get('message'))
        self.assertEqual(job['result']['cues'][0]['text'], '战略之助动力电池')

    def test_style_preset_survives_app_restart_with_new_session(self):
        style = {'font': 'Microsoft YaHei', 'size': 56, 'color': '#ddeeff', 'outline': 2, 'shadow': 1, 'background': False, 'margin': 80, 'position': 'bottom'}
        self.assertEqual(self.post('style-preset', style).status_code, 200)
        restarted = app.create_app(Path(self.temp.name))
        state = restarted.test_client().get('/api/state', headers={'X-App-Token': restarted.config['APP_TOKEN']}).get_json()
        self.assertEqual(state['style_preset'], style)

    def test_drop_upload_cannot_escape_cache_directory(self):
        response = self.client.post('/api/upload', data={'file': (io.BytesIO(b'1\n00:00:00,000 --> 00:00:01,000\nHello\n'), '../../danger.srt')}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        saved = Path(response.get_json()['path']).resolve()
        self.assertTrue(saved.is_relative_to(Path(self.temp.name).resolve()))
        self.assertTrue(saved.exists())

    def test_real_ffmpeg_burn_produces_playable_video(self):
        source = Path(self.temp.name) / 'source.mp4'
        subprocess.run([app.executable('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=navy:s=320x180:d=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(source)], check=True, creationflags=app.HIDDEN)
        state = self.client.get('/api/state', headers=self.headers).get_json()
        project = state['project']
        project['media'] = app.probe(source)
        project['cues'] = [{'start': 0, 'end': .9, 'text': '字幕导出测试'}]
        output = Path(self.temp.name) / '带 字幕.mp4'
        response = self.post('jobs', {'kind': 'burn', 'project': project, 'path': str(output)})
        self.assertEqual(response.status_code, 200)
        identifier = response.get_json()['job']['id']
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job = self.client.get('/api/jobs/' + identifier, headers=self.headers).get_json()['job']
            if job['state'] not in ('running', 'cancelling'):
                break
            time.sleep(.1)
        self.assertEqual(job['state'], 'done', job['message'])
        metadata = app.probe(output)
        self.assertEqual((metadata['width'], metadata['height']), (320, 180))
        self.assertGreater(metadata['duration'], .9)

    def test_import_edit_save_and_export_project(self):
        source = Path(self.temp.name) / 'sample.srt'
        source.write_text('1\n00:00:00,000 --> 00:00:02,000\n你好世界\n', encoding='utf-8')
        cues = self.post('import-subtitles', {'path': str(source)}).get_json()['cues']
        state = self.client.get('/api/state', headers=self.headers).get_json()
        project = state['project']
        project['cues'] = cues
        self.assertEqual(self.post('project', project).status_code, 200)
        target = Path(self.temp.name) / 'edited.srt'
        response = self.post('export-text', {'project': project, 'path': str(target), 'format': 'srt'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('你好世界', target.read_text(encoding='utf-8-sig'))

    def test_training_is_explicit_persistent_and_can_be_removed(self):
        source = Path(self.temp.name) / 'example.srt'
        source.write_text('1\n00:00:00,000 --> 00:00:01,000\n你好世界\n', encoding='utf-8')
        result = self.post('learn', {'profile_id': 'default', 'paths': [str(source)]}).get_json()
        self.assertEqual(result['profile']['stats']['cue_count'], 1)
        state = self.client.get('/api/state', headers=self.headers).get_json()
        self.assertEqual(len(state['profiles'][0]['samples']), 1)
        result = self.post('forget', {'profile_id': 'default'}).get_json()
        self.assertEqual(result['profile']['samples'], [])

    def test_export_cannot_overwrite_source_media(self):
        state = self.client.get('/api/state', headers=self.headers).get_json()
        project = state['project']
        source = Path(self.temp.name) / 'video.mp4'
        source.write_bytes(b'original media')
        project['media'] = {'path': str(source)}
        project['cues'] = [{'start': 0, 'end': 1, 'text': 'hello'}]
        response = self.post('export-text', {'project': project, 'path': str(source), 'format': 'srt'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(source.read_bytes(), b'original media')


if __name__ == '__main__':
    unittest.main()
