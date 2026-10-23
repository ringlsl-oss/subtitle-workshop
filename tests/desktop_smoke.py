"""Manual smoke command: python tests/desktop_smoke.py (opens a hidden WebView2)."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import webview
if os.environ.get('SUBTITLE_FIXED_WEBVIEW2'):
    webview.settings['WEBVIEW2_RUNTIME_PATH'] = os.environ['SUBTITLE_FIXED_WEBVIEW2']
from werkzeug.serving import make_server

with tempfile.TemporaryDirectory() as folder:
    application = app.create_app(Path(folder))
    server = make_server('127.0.0.1', 0, application, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    bridge = app.DesktopApi()
    window = webview.create_window('字幕工坊启动验证', f'http://127.0.0.1:{server.server_port}', js_api=bridge, hidden=True)
    bridge._window = window
    errors = []
    def verify():
        try:
            result = window.evaluate_js("({title:document.title,api:typeof window.pywebview.api.choose,editor:!!document.getElementById('cueList'),icon:document.querySelector('.brand-mark').naturalWidth>0})")
            assert result == {'title': '字幕工坊', 'api': 'function', 'editor': True, 'icon': True}, result
            print('DESKTOP_SMOKE_OK ' + json.dumps(result, ensure_ascii=True), flush=True)
        except Exception as error:
            errors.append(error)
            print(repr(error), flush=True)
        finally:
            window.destroy()
    window.events.loaded += verify
    webview.start(gui='edgechromium', icon=str(app.ROOT/'web'/'app-icon.ico'))
    server.shutdown()
    if errors:
        raise SystemExit(1)
