"""Local document extraction and conservative, reviewable text alignment."""
import copy
from difflib import SequenceMatcher
from pathlib import Path
import unicodedata
import zipfile
from xml.etree import ElementTree

import core

MAX_CHARS = 20000


def validate_document(document):
    text = document.get('text', '') if isinstance(document, dict) else ''
    if not isinstance(text, str) or not text.strip():
        raise ValueError('文稿没有可读取的文字，请导入正文或粘贴文字')
    if len(text) > MAX_CHARS:
        raise ValueError('文稿最多支持 20000 字，请按视频片段拆分文稿')
    if not any(c.isalnum() for c in text):
        raise ValueError('文稿没有可用于校对的文字')
    return {'name': str(document.get('name') or '粘贴的文稿')[:200], 'text': text.strip()}


def read_document(path):
    path = Path(path)
    if path.suffix.lower() not in ('.docx', '.txt', '.md'):
        raise ValueError('支持 Word .docx、TXT、Markdown；其他格式请另存为 DOCX / TXT 或粘贴正文')
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('文档超过 20 MB，请移除图片或另存为纯文本')
    if path.suffix.lower() == '.docx':
        try:
            with zipfile.ZipFile(path) as package:
                if package.getinfo('word/document.xml').file_size > 8 * 1024 * 1024:
                    raise ValueError('Word 正文过大，请分段导入')
                xml = package.read('word/document.xml')
            if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
                raise ValueError('不支持的 Word XML 格式')
            root = ElementTree.fromstring(xml)
            ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            paragraphs = []
            for paragraph in root.iter(ns + 'p'):
                paragraphs.append(''.join(node.text or '' if node.tag == ns + 't' else '\n' if node.tag == ns + 'br' else '\t' if node.tag == ns + 'tab' else '' for node in paragraph.iter()).strip())
            text = '\n'.join(p for p in paragraphs if p)
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as error:
            raise ValueError('无法读取 Word 文档，请另存为 DOCX 或 TXT 后重试') from error
    else:
        raw = path.read_bytes()
        encodings = ['utf-16'] if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ['utf-8-sig', 'gb18030']
        for encoding in encodings:
            try:
                text = raw.decode(encoding)
                break
            except UnicodeError:
                continue
        else:
            raise ValueError('无法识别文本编码，请另存为 UTF-8 文本')
        if '\x00' in text:
            raise ValueError('文件不是可读取的文本，请另存为 UTF-8 文本')
    return validate_document({'name': path.name, 'text': text})


def normalized(text):
    """Keep offsets into original text while ignoring case, punctuation and script."""
    chars, offsets = [], []
    converter = core.simplified_converter()
    for offset, char in enumerate(text):
        for value in converter.convert(unicodedata.normalize('NFKC', char)).lower():
            numeric_separator = value in '.-+/:,' and ((offset > 0 and text[offset - 1].isdigit()) or (offset + 1 < len(text) and text[offset + 1].isdigit()))
            if value.isalnum() or value in '%‰¥$€℃°' or numeric_separator:
                chars.append(value)
                offsets.append(offset)
    return ''.join(chars), offsets


def compare(cues, document):
    document = validate_document(document)
    core.validate_cues(cues)
    if not cues:
        raise ValueError('请先自动识别或导入字幕，再与文稿对照')
    if sum(len(c['text']) for c in cues) > MAX_CHARS:
        raise ValueError('单次对照最多支持 20000 字字幕，请分段校对')
    source, positions = '', []
    for index, cue in enumerate(cues):
        text, offsets = normalized(cue['text'])
        source += text
        positions.extend((index, offset) for offset in offsets)
    target, target_offsets = normalized(document['text'])
    matcher = SequenceMatcher(None, source, target, autojunk=False)
    ratio = matcher.ratio()
    low_match = ratio < .55
    rows, by_cue, affected = [], {}, set()
    for kind, a, b, c, d in matcher.get_opcodes():
        if kind == 'equal':
            continue
        doc_text = document['text'][target_offsets[c]:target_offsets[d - 1] + 1] if c < d else ''
        indices = sorted({i for i, _ in positions[a:b]})
        # Inserts at cue boundaries have no reliable spoken timing.
        internal_insert = kind == 'insert' and 0 < a < len(positions) and positions[a - 1][0] == positions[a][0]
        if internal_insert:
            indices = [positions[a][0]]
        difference = {'kind': kind, 'recognized': source[a:b], 'document': doc_text}
        if not indices:
            rows.append({'kind': 'document_only', 'cue_index': None, 'original': '', 'suggestion': None,
                         'document': doc_text, 'differences': [difference], 'reason': '文稿中有这段文字，但未定位到对应语音；请核对是否漏读或漏识别。'})
            continue
        affected.update(indices)
        safe = not low_match and len(indices) == 1 and max(b - a, d - c) <= 12
        for index in indices:
            if index not in by_cue:
                row = {'kind': 'different', 'cue_index': index, 'original': cues[index]['text'], 'suggestion': None,
                       'document': '', 'differences': [], 'reason': '', '_edits': [], '_safe': True}
                by_cue[index] = row
                rows.append(row)
            row = by_cue[index]
            row['differences'].append(difference)
            row['_safe'] &= safe
            if safe:
                start = positions[a][1]
                end = positions[b - 1][1] + 1 if b > a else start
                replacement = core.simplified_converter().convert(doc_text)
                row['_edits'].append((start, end, replacement))
    for row in by_cue.values():
        candidate = row['original']
        if row.pop('_safe'):
            for start, end, text in reversed(row['_edits']):
                candidate = candidate[:start] + text + candidate[end:]
            if candidate.strip():
                row['suggestion'] = candidate
        row.pop('_edits')
        row['reason'] = '可选择采用文稿文字；请先试听确认，文稿也可能有误。' if row['suggestion'] is not None else '匹配不足、差异过长或跨字幕，需试听后手动修改。'
    return {'document': document, 'source_cues': copy.deepcopy(cues), 'rows': rows,
            'similarity': round(ratio * 100), 'low_match': low_match,
            'matched_cues': len(cues) - len(affected), 'checked_at': core.now()}
