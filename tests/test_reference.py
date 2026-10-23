import copy
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import app


def client(tmp_path):
    application = app.create_app(tmp_path)
    return application, application.test_client(), {'X-App-Token': application.config['APP_TOKEN']}


def test_import_word_paragraphs_and_tables_and_gbk_text(tmp_path):
    _, http, headers = client(tmp_path)
    word = tmp_path / '文稿.docx'
    with zipfile.ZipFile(word, 'w') as package:
        package.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>示例中学</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>欢迎你</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
    result = http.post('/api/import-document', json={'path': str(word)}, headers=headers)
    assert result.status_code == 200
    assert result.json['document']['text'] == '示例中学\n欢迎你'
    text = tmp_path / '解说.txt'
    text.write_bytes('这是中文文稿'.encode('gb18030'))
    result = http.post('/api/import-document', json={'path': str(text)}, headers=headers)
    assert result.json['document']['text'] == '这是中文文稿'


def test_compare_changes_keeps_timing_and_originals(tmp_path):
    _, http, headers = client(tmp_path)
    cues = [{'start': 1, 'end': 3, 'text': '欢迎来到示列中学', 'words': []},
            {'start': 3, 'end': 6, 'text': '今天我们一起出发'}]
    before = copy.deepcopy(cues)
    result = http.post('/api/compare-document', json={'cues': cues, 'document': {'text': '欢迎来到示例中学。今天，我们一起出发！'}}, headers=headers)
    assert result.status_code == 200
    report = result.json['comparison']
    assert report['source_cues'] == before
    assert len(report['rows']) == 1
    assert report['rows'][0]['suggestion'] == '欢迎来到示例中学'
    assert report['rows'][0]['cue_index'] == 0
    assert report['rows'][0]['differences'][0]['recognized'] == '列'
    assert report['rows'][0]['differences'][0]['document'] == '例'
    assert report['matched_cues'] == 1


def test_unspoken_document_sections_are_not_inserted_into_subtitles(tmp_path):
    _, http, headers = client(tmp_path)
    cues = [{'start': 0, 'end': 2, 'text': '欢迎来到示例中学'}, {'start': 3, 'end': 5, 'text': '今天我们一起出发'}]
    result = http.post('/api/compare-document', json={'cues': cues, 'document': {'text': '宣传片文案\n欢迎来到示例中学\n这里是只写在纸上没有读出的段落\n今天我们一起出发'}}, headers=headers)
    assert result.status_code == 200
    rows = result.json['comparison']['rows']
    assert any(r['kind'] == 'document_only' for r in rows)
    assert all(r['suggestion'] is None for r in rows)


def test_unrelated_document_and_cross_cue_replacements_require_manual_review(tmp_path):
    _, http, headers = client(tmp_path)
    result = http.post('/api/compare-document', json={'cues': [{'start': 0, 'end': 2, 'text': '示例中学欢迎你'}], 'document': {'text': '苹果香蕉西瓜芒果'}}, headers=headers)
    assert result.status_code == 200
    assert result.json['comparison']['low_match']
    assert all(r['suggestion'] is None for r in result.json['comparison']['rows'])


def test_numbers_decimal_points_and_percentages_are_meaningful(tmp_path):
    _, http, headers = client(tmp_path)
    for spoken, written in [('增长率为35%', '增长率为3.5%'), ('今年增长率为50', '今年增长率为50%')]:
        result = http.post('/api/compare-document', json={'cues': [{'start': 0, 'end': 2, 'text': spoken}], 'document': {'text': written}}, headers=headers)
        assert result.status_code == 200
        assert result.json['comparison']['rows'], 'Numeric symbols must not be treated as decorative punctuation'
    result = http.post('/api/compare-document', json={'cues': [{'start': 0, 'end': 2, 'text': '欢迎来到甲'}, {'start': 2, 'end': 4, 'text': '乙中学一起学习'}], 'document': {'text': '欢迎来到示例中学一起学习'}}, headers=headers)
    assert all(r['suggestion'] is None for r in result.json['comparison']['rows'])


def test_document_validation_and_project_persistence(tmp_path):
    application, http, headers = client(tmp_path)
    for text in ('', ' ' * 5, 'a' * 20001):
        result = http.post('/api/compare-document', json={'cues': [], 'document': {'text': text}}, headers=headers)
        assert result.status_code == 400
    project = http.get('/api/state', headers=headers).json['project']
    project['reference_document'] = {'name': '解说词', 'text': '示例中学欢迎你'}
    assert http.post('/api/project', json=project, headers=headers).status_code == 200
    assert application.config['STORE'].load_project()['reference_document'] == project['reference_document']


def test_recognition_compares_document_without_biasing_worker_prompt(tmp_path):
    application, http, headers = client(tmp_path)
    media = tmp_path / 'test.wav'
    media.touch()
    with patch.object(application.config['JOBS'], 'start', return_value={'id': 'queued'}) as launch:
        response = http.post('/api/jobs', json={'kind': 'transcribe', 'path': str(media), 'model': 'tiny', 'reference_document': {'name': '文稿', 'text': '欢迎来到示例中学'}}, headers=headers)
        assert response.status_code == 200
        data = launch.call_args.args[1]
    (tmp_path / 'transcribe_worker.py').write_text("import sys,json\nfrom pathlib import Path\ndata=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))\nassert 'reference_document' not in data\nPath(sys.argv[2]).write_text(" + repr(json.dumps([{'start': 0, 'end': 2, 'text': '欢迎来到示列中学'}])) + ",encoding='utf-8')", encoding='utf-8')
    job = {'id': 'reference', 'kind': 'transcribe', 'state': 'running'}
    with patch.object(app, 'ROOT', tmp_path):
        application.config['JOBS'].run(job, data)
    assert job['state'] == 'done', job.get('message')
    assert job['result']['comparison']['rows'][0]['suggestion'] == '欢迎来到示例中学'
    assert job['result']['cues'][0]['text'] == '欢迎来到示列中学'
