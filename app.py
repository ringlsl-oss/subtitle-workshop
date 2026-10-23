"""Local desktop application entry point."""
import argparse
import copy
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from flask import Flask, jsonify, request, send_file
from werkzeug.serving import make_server
import core
import reference

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def executable(name):
    bundled = ROOT / 'bin' / (name + '.exe')
    value = str(bundled) if bundled.exists() else shutil.which(name)
    if not value:
        raise ValueError(f'找不到 {name}，请安装 FFmpeg 并加入 PATH')
    return value


def probe(path):
    import av
    path = Path(path).resolve(strict=True)
    with av.open(str(path)) as container:
        video = next(iter(container.streams.video), None)
        width, height = (video.width, video.height) if video else (1920, 1080)
        if video:
            rotation = int(float(video.metadata.get('rotate', 0)))
            if abs(rotation) % 180 == 90:
                width, height = height, width
        duration = float(container.duration / av.time_base) if container.duration else max((float(s.duration * s.time_base) for s in container.streams if s.duration and s.time_base), default=0)
        return dict(path=str(path), name=path.name, duration=duration, width=width, height=height, has_video=video is not None, has_audio=bool(container.streams.audio))


def python_runtime():
    settings = ROOT / 'runtime.json'
    if settings.exists():
        path = Path(json.loads(settings.read_text(encoding='utf-8'))['python'])
        if not path.is_absolute():
            path = ROOT / path
        if path.is_file():
            return str(path.resolve())
        raise ValueError('识别运行环境不完整，请重新解压完整的软件文件夹')
    if not getattr(sys, 'frozen', False):
        return sys.executable
    path = shutil.which('python')
    if not path:
        raise ValueError('未找到语音识别运行环境，请安装 Python 和 openai-whisper')
    return path


class Jobs:
    def __init__(self, root, store=None):
        self.root = root
        self.store = store or core.Store(root)
        self.jobs = {}
        self.lock = threading.RLock()

    def start(self, kind, data):
        with self.lock:
            if any(j['state'] in ('running', 'cancelling') for j in self.jobs.values()):
                raise ValueError('请先等待当前任务完成，或取消当前任务')
            job = dict(id=uuid.uuid4().hex, kind=kind, state='running', progress=0, message='正在准备…', result=None)
            self.jobs[job['id']] = job
            threading.Thread(target=self.run, args=(job, copy.deepcopy(data)), daemon=True).start()
            return self.public(job)

    def public(self, job):
        with self.lock:
            return {k: v for k, v in job.items() if k != 'process'}

    def cancel(self, identifier):
        with self.lock:
            job = self.jobs[identifier]
            if job['state'] == 'running':
                job['state'] = 'cancelling'
                job['message'] = '正在取消…'
                process = job.get('process')
                if process and process.poll() is None:
                    process.kill()
            return self.public(job)

    def launch(self, job, args, **kwargs):
        with self.lock:
            if job['state'] == 'cancelling':
                raise InterruptedError()
            process = subprocess.Popen(args, creationflags=HIDDEN, **kwargs)
            job['process'] = process
            return process

    def run(self, job, data):
        temp_output = None
        try:
            with tempfile.TemporaryDirectory(prefix='subtitle-') as folder:
                folder = Path(folder)
                if job['kind'] == 'transcribe':
                    job['message'] = '正在加载本地模型；首次使用未缓存模型时需要下载'
                    input_path = folder / 'request.json'
                    output_path = folder / 'result.json'
                    worker_data = {k: v for k, v in data.items() if k not in ('reference_document', '_profile')}
                    input_path.write_text(json.dumps(worker_data, ensure_ascii=False), encoding='utf-8')
                    process = self.launch(job, [python_runtime(), '-u', str(ROOT / 'transcribe_worker.py'), str(input_path), str(output_path)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
                    tail = []
                    for line in process.stdout:
                        tail.append(line.strip())
                        tail = tail[-15:]
                        if line.startswith('PROGRESS '):
                            update = json.loads(line[9:])
                            job.update(update)
                    process.wait()
                    if process.returncode:
                        raise ValueError('\n'.join(tail)[-1800:])
                    cues = json.loads(output_path.read_text(encoding='utf-8'))
                    cues = core.simplify_cues(cues)
                    selected_profile = data.get('_profile')
                    job['result'] = {'cues': core.resegment(cues, selected_profile) if selected_profile else cues, 'original_cues': cues, 'application': core.application_info(selected_profile) if selected_profile else None}
                    if data.get('reference_document'):
                        job['message'] = '语音识别完成，正在与文稿对照…'
                        try:
                            job['result']['comparison'] = reference.compare(job['result']['cues'], data['reference_document'])
                        except ValueError as error:
                            job['result']['comparison_error'] = str(error)
                else:
                    media = data['project']['media'] if job['kind'] == 'burn' else data['media']
                    duration = max(.001, media['duration'])
                    output = Path(data['path']).resolve()
                    if output == Path(media['path']).resolve():
                        raise ValueError('不能覆盖原始媒体，请另选导出文件名')
                    output.parent.mkdir(parents=True, exist_ok=True)
                    temp_output = output.with_name(output.stem + '.' + job['id'] + '.partial.mp4')
                    args = [executable('ffmpeg'), '-hide_banner', '-y', '-i', media['path']]
                    if job['kind'] == 'burn':
                        project = data['project']
                        (folder / 'subtitles.ass').write_text(core.to_ass(project['cues'], project['style'], media['width'], media['height']), encoding='utf-8-sig')
                        args += ['-vf', 'ass=subtitles.ass']
                    else:
                        args += ['-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2']
                    args += ['-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18' if job['kind'] == 'burn' else '24', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-progress', 'pipe:1', '-nostats', str(temp_output)]
                    log = folder / 'ffmpeg.log'
                    with log.open('w', encoding='utf-8') as error_stream:
                        process = self.launch(job, args, cwd=folder, stdout=subprocess.PIPE, stderr=error_stream, encoding='utf-8', errors='replace')
                        job['message'] = '正在导出视频…' if job['kind'] == 'burn' else '正在生成兼容预览…'
                        for line in process.stdout:
                            if line.startswith('out_time_ms='):
                                try:
                                    job['progress'] = min(99, int(float(line.split('=')[1]) / 1000000 / duration * 100))
                                except ValueError:
                                    pass
                        process.wait()
                    if process.returncode:
                        raise ValueError(log.read_text(encoding='utf-8')[-1800:])
                    with self.lock:
                        if job['state'] == 'cancelling':
                            raise InterruptedError()
                        temp_output.replace(output)
                    job['result'] = {'path': str(output)}
                    if job['kind'] == 'burn':
                        job['result']['output'] = self.store.record_output(output, 'mp4', data['project']['name'])
                with self.lock:
                    if job['state'] == 'cancelling':
                        raise InterruptedError()
                    job.update(state='done', progress=100, message='已完成')
        except Exception as error:
            cancelled = job['state'] == 'cancelling' or isinstance(error, InterruptedError)
            job.update(state='cancelled' if cancelled else 'error', message='已取消' if cancelled else str(error) or type(error).__name__)
        finally:
            if temp_output and temp_output.exists():
                temp_output.unlink()
            job.pop('process', None)


def create_app(data_root=None):
    default_root = APP_ROOT / 'data' if (APP_ROOT / 'portable.flag').exists() else Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'SubtitleWorkshop'
    data_root = Path(data_root or os.environ.get('SUBTITLE_DATA_DIR') or default_root)
    store = core.Store(data_root)
    jobs = Jobs(data_root, store)
    app = Flask(__name__, static_folder=str(ROOT / 'web'), static_url_path='/assets')
    app.config['APP_TOKEN'] = secrets.token_urlsafe(32)
    app.config['STORE'] = store
    app.config['JOBS'] = jobs
    resources = {}

    def attach_media(media):
        if media and Path(media['path']).exists():
            key = uuid.uuid4().hex
            resources[key] = media['path']
            media['url'] = f'/media/{key}?token={app.config["APP_TOKEN"]}'
        return media

    @app.before_request
    def authorize():
        if request.path.startswith('/api/') and request.headers.get('X-App-Token') != app.config['APP_TOKEN']:
            return jsonify(error='会话已失效，请重新打开软件'), 403

    @app.errorhandler(Exception)
    def handle(error):
        from werkzeug.exceptions import HTTPException
        status = error.code if isinstance(error, HTTPException) else 400
        return jsonify(error=str(error)), status

    @app.get('/')
    def index():
        content = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
        return content.replace('__APP_TOKEN__', app.config['APP_TOKEN'])

    @app.get('/media/<key>')
    def media_file(key):
        if request.args.get('token') != app.config['APP_TOKEN'] or key not in resources:
            return '', 403
        return send_file(resources[key], conditional=True)

    @app.get('/api/state')
    def state():
        project = store.load_project()
        project['media'] = attach_media(project.get('media'))
        return jsonify(project=project, profiles=store.profiles(), outputs=store.read('outputs.json', []), style_preset=store.read('style-preset.json', None), data_dir=str(data_root), ffmpeg=bool(shutil.which('ffmpeg') or (ROOT / 'bin' / 'ffmpeg.exe').exists()))

    @app.get('/api/outputs')
    def outputs():
        return jsonify(outputs=store.read('outputs.json', []))

    def output_entry(identifier):
        entry = next((r for r in store.read('outputs.json', []) if r['id'] == identifier), None)
        if not entry or not Path(entry['path']).is_file():
            raise ValueError('文件已移动或删除，请检查保存路径')
        return entry

    @app.post('/api/output-preview')
    def output_preview():
        entry = output_entry(request.json['id'])
        if entry['format'] == 'mp4':
            return jsonify(media=attach_media({'path':entry['path']}))
        with Path(entry['path']).open(encoding='utf-8-sig') as file:
            text = file.read(200000)
        return jsonify(text=text)

    @app.post('/api/open-output-folder')
    def open_output_folder():
        folder = Path(output_entry(request.json['id'])['path']).parent if request.json.get('id') else data_root
        os.startfile(str(folder))
        return jsonify(ok=True)

    @app.post('/api/style-preset')
    def style_preset():
        style = {**core.DEFAULT_STYLE, **request.json}
        core.to_ass([], style)
        store.write('style-preset.json', style)
        return jsonify(ok=True)

    @app.post('/api/media')
    def media():
        return jsonify(media=attach_media(probe(request.json['path'])))

    @app.post('/api/import-subtitles')
    def import_subtitles():
        return jsonify(cues=core.read_subtitles(request.json['path']))

    @app.post('/api/import-document')
    def import_document():
        return jsonify(document=reference.read_document(request.json['path']))

    @app.post('/api/compare-document')
    def compare_document():
        return jsonify(comparison=reference.compare(request.json['cues'], request.json['document']))

    @app.post('/api/upload')
    def upload():
        file = request.files['file']
        suffix = Path(file.filename).suffix.lower()
        if suffix not in ('.srt', '.ass', '.ssa', '.mp4', '.mov', '.mkv', '.avi', '.webm', '.mp3', '.wav', '.m4a', '.flac'):
            raise ValueError('不支持的文件类型')
        cache = data_root / 'imports'
        cache.mkdir(exist_ok=True)
        target = cache / (uuid.uuid4().hex + suffix)
        file.save(target)
        return jsonify(path=str(target))

    @app.post('/api/project')
    def save_project():
        store.save_project(request.json)
        return jsonify(ok=True)

    @app.post('/api/open-project')
    def open_project():
        project = json.loads(Path(request.json['path']).read_text(encoding='utf-8-sig'))
        if project.get('version') != 1:
            raise ValueError('不支持的项目版本')
        core.validate_cues(project['cues'])
        project['media'] = attach_media(project.get('media'))
        return jsonify(project=project)

    @app.post('/api/export-text')
    def export_text():
        data = request.json
        project, path = data['project'], Path(data['path']).resolve()
        if project.get('media') and path == Path(project['media']['path']).resolve():
            raise ValueError('不能覆盖原始媒体，请另选文件名')
        core.validate_cues(project['cues'])
        kind = data['format']
        if kind == 'project':
            value = json.dumps(project, ensure_ascii=False, indent=2)
        elif kind == 'srt':
            value = core.to_srt(project['cues'])
        elif kind == 'ass':
            media = project.get('media') or {}
            value = core.to_ass(project['cues'], project['style'], media.get('width', 1920), media.get('height', 1080))
        elif kind == 'txt':
            value = '\n'.join(c['text'] for c in project['cues'])
        else:
            raise ValueError('不支持的导出格式')
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        temp.write_text(value, encoding='utf-8-sig')
        temp.replace(path)
        entry = store.record_output(path, kind, project['name'])
        return jsonify(path=str(path), output=entry)

    def get_profile(identifier):
        profiles = store.profiles()
        profile = next((p for p in profiles if p['id'] == identifier), None)
        if profile is None:
            raise ValueError('未找到所选习惯')
        return profiles, profile

    @app.post('/api/profile')
    def profile_save():
        incoming = request.json
        profiles = store.profiles()
        if incoming.get('id'):
            _, profile = get_profile(incoming['id'])
            profile['rules'] = incoming['rules']
            profile['name'] = incoming['name']
            r = profile['rules']
            if not (2 <= int(r['target_chars']) <= int(r['max_chars']) <= 100 and 2 <= int(r['line_chars']) <= 100 and int(r['max_lines']) in (1, 2) and 0 <= float(r['pause']) <= 5):
                raise ValueError('请检查断句规则：常用字数不能超过最大字数，字数范围为 2～100')
            profiles = [profile if p['id'] == profile['id'] else p for p in profiles]
        else:
            profile = core.new_profile(incoming['name'].strip() or '新习惯')
            profiles.append(profile)
        profile['saved_at'] = core.now()
        store.write('profiles.json', profiles)
        return jsonify(profile=profile, profiles=profiles)

    @app.post('/api/learn')
    def learn():
        data = request.json
        profiles, profile = get_profile(data['profile_id'])
        errors = []
        report = dict(added=0, duplicates=0, updated=0, failed=0, saved_at=core.now())
        for path in data.get('paths', []):
            try:
                count = len(profile['samples'])
                core.learn(profile, core.read_subtitles(path), Path(path).name)
                report['added' if len(profile['samples']) > count else 'duplicates'] += 1
            except Exception as error:
                errors.append(f'{Path(path).name}：{error}')
        if data.get('cues'):
            old_samples = copy.deepcopy(profile['samples'])
            core.learn(profile, data['cues'], data.get('name', '确认成稿'), data.get('source_id'))
            report['duplicates' if profile['samples'] == old_samples else 'added' if len(profile['samples']) > len(old_samples) else 'updated'] += 1
        report['failed'] = len(errors)
        report['errors'] = errors
        profile['last_learning'] = report
        store.write('profiles.json', profiles)
        return jsonify(profile=profile, profiles=profiles, errors=errors, report=report)

    @app.post('/api/forget')
    def forget():
        profiles, profile = get_profile(request.json['profile_id'])
        profile = core.new_profile(profile['name'], profile['id'])
        profiles = [profile if p['id'] == profile['id'] else p for p in profiles]
        store.write('profiles.json', profiles)
        return jsonify(profile=profile, profiles=profiles)

    @app.post('/api/resegment')
    def segment():
        _, profile = get_profile(request.json['profile_id'])
        return jsonify(cues=core.resegment(request.json['cues'], profile), application=core.application_info(profile))

    @app.post('/api/simplify')
    def simplify():
        return jsonify(cues=core.simplify_cues(request.json['cues']))

    @app.post('/api/jobs')
    def start_job():
        data = request.json
        kind = data.pop('kind')
        if kind not in ('burn', 'transcribe', 'preview'):
            raise ValueError('不支持的任务')
        if kind == 'burn':
            core.validate_cues(data['project']['cues'])
            if not data['project']['cues'] or not data['project'].get('media', {}).get('has_video'):
                raise ValueError('请先导入视频并添加字幕')
        if kind == 'transcribe':
            if data.get('reference_document') is not None:
                data['reference_document'] = reference.validate_document(data['reference_document'])
            _, selected_profile = get_profile(data.get('profile_id', 'default'))
            data['_profile'] = copy.deepcopy(selected_profile)
            if data['model'] not in ('tiny', 'base', 'small', 'medium'):
                raise ValueError('不支持的模型')
            if not Path(data['path']).is_file():
                raise ValueError('原始媒体文件已移动，请重新导入')
        if kind == 'preview':
            data['path'] = str(data_root / ('preview-' + uuid.uuid4().hex + '.mp4'))
        return jsonify(job=jobs.start(kind, data))

    @app.get('/api/jobs/<identifier>')
    def job_status(identifier):
        job = jobs.public(jobs.jobs[identifier])
        if job['state'] == 'done' and job['kind'] == 'preview':
            job = copy.deepcopy(job)
            job['result']['media'] = attach_media(probe(job['result']['path']))
        return jsonify(job=job)

    @app.post('/api/jobs/<identifier>/cancel')
    def cancel(identifier):
        return jsonify(job=jobs.cancel(identifier))

    return app


class DesktopApi:
    def __init__(self):
        self._window = None

    def choose(self, kind, multiple=False, filename=''):
        import webview
        types = {
            'media': ('视频与音频 (*.mp4;*.mov;*.mkv;*.avi;*.webm;*.mp3;*.wav;*.m4a;*.flac)',),
            'subtitles': ('字幕 (*.srt;*.ass;*.ssa)',),
            'document': ('文稿 (*.docx;*.txt;*.md)',),
            'project': ('字幕工坊项目 (*.zmproj)',),
            'srt': ('SRT 字幕 (*.srt)',), 'ass': ('ASS 字幕 (*.ass)',),
            'txt': ('文本 (*.txt)',), 'mp4': ('视频 (*.mp4)',),
        }
        save = bool(filename)
        result = self._window.create_file_dialog(webview.FileDialog.SAVE if save else webview.FileDialog.OPEN, allow_multiple=multiple, save_filename=filename, file_types=types[kind])
        if not result:
            return []
        return list(result) if isinstance(result, (list, tuple)) else [result]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    app = create_app()
    server = make_server('127.0.0.1', args.port, app, threaded=True)
    url = f'http://127.0.0.1:{server.server_port}'
    if args.browser:
        print(url, flush=True)
        server.serve_forever()
    else:
        import webview
        fixed_runtime = ROOT / 'webview2'
        if (fixed_runtime / 'msedgewebview2.exe').is_file():
            webview.settings['WEBVIEW2_RUNTIME_PATH'] = str(fixed_runtime)
            if os.name == 'nt' and sys.getwindowsversion().build < 22000:
                # Microsoft requires app-container read access for fixed WebView2 on Windows 10.
                for sid in ('*S-1-15-2-2:(OI)(CI)(RX)', '*S-1-15-2-1:(OI)(CI)(RX)'):
                    subprocess.run(['icacls', str(fixed_runtime), '/grant', sid], creationflags=HIDDEN, capture_output=True, timeout=30, check=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        api = DesktopApi()
        api._window = webview.create_window('字幕工坊', url, js_api=api, width=1440, height=940, min_size=(1060, 720), background_color='#151918')
        def close():
            for identifier in list(app.config['JOBS'].jobs):
                app.config['JOBS'].cancel(identifier)
            server.shutdown()
        api._window.events.closed += close
        webview.start(gui='edgechromium', icon=str(ROOT / 'web' / 'app-icon.ico'))


if __name__ == '__main__':
    main()
