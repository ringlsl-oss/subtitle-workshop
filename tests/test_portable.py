import json
from pathlib import Path
from unittest.mock import patch
import pytest
import app
import transcribe_worker
import sys


def test_source_checkout_uses_its_active_environment_without_local_config(tmp_path):
    with patch.object(app, 'ROOT', tmp_path):
        assert app.python_runtime() == sys.executable


def test_python_path_is_relative_to_bundle_not_working_directory(tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime' / 'python.exe'
    runtime.parent.mkdir()
    runtime.touch()
    (tmp_path / 'runtime.json').write_text(json.dumps({'python': 'runtime/python.exe'}))
    monkeypatch.chdir(tmp_path.parent)
    with patch.object(app, 'ROOT', tmp_path):
        assert Path(app.python_runtime()) == runtime


def test_declared_missing_runtime_does_not_silently_use_developer_python(tmp_path):
    (tmp_path / 'runtime.json').write_text(json.dumps({'python': 'runtime/missing.exe'}))
    with patch.object(app, 'ROOT', tmp_path), pytest.raises(ValueError, match='运行环境'):
        app.python_runtime()


def test_portable_data_is_separate_from_existing_user_projects(tmp_path, monkeypatch):
    monkeypatch.delenv('SUBTITLE_DATA_DIR', raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'private'))
    (tmp_path / 'portable.flag').touch()
    with patch.object(app, 'APP_ROOT', tmp_path, create=True):
        application = app.create_app()
    assert application.config['STORE'].root == tmp_path / 'data'
    assert application.config['STORE'].load_project()['cues'] == []


def test_worker_uses_bundled_model_cache(tmp_path):
    (tmp_path / 'runtime.json').write_text(json.dumps({'models': 'models'}))
    with patch.object(transcribe_worker, '__file__', str(tmp_path / 'transcribe_worker.py')):
        assert transcribe_worker.configure_runtime()['models'] == str(tmp_path / 'models')
