"""Subtitle parsing, personal segmentation and local project storage."""
import copy
import hashlib
import json
import math
import re
import statistics
import threading
import uuid
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def application_info(profile):
    return dict(profile_id=profile['id'], name=profile['name'], sample_count=len(profile['samples']), cue_count=sum(len(s['cues']) for s in profile['samples']), rules=copy.deepcopy(profile['rules']), applied_at=now())

PUNCT = '，。！？；：,.!?;:'
DEFAULT_STYLE = dict(font='Microsoft YaHei', size=48, color='#f5f5f2', outline=2, shadow=1, background=False, margin=60, position='bottom')


@lru_cache(maxsize=1)
def simplified_converter():
    from opencc import OpenCC
    return OpenCC('t2s')


def simplify_cues(cues):
    """Convert text in phrase context without changing cue or word times."""
    validate_cues(cues)
    result = copy.deepcopy(cues)
    converter = simplified_converter()
    for cue in result:
        original = cue['text']
        cue['text'] = converter.convert(original)
        if cue['text'] == original:
            continue
        words = cue.get('words')
        if words:
            original_flat, converted_flat = flat(original), flat(cue['text'])
            if ''.join(w['word'] for w in words) == original_flat and len(original_flat) == len(converted_flat):
                offset = 0
                for word in words:
                    end = offset + len(word['word'])
                    word['word'] = converted_flat[offset:end]
                    offset = end
            else:
                # Do not retain a stale alignment after phrase-length changes.
                cue.pop('words', None)
    return result


def validate_cues(cues):
    if not isinstance(cues, list):
        raise ValueError('字幕格式不正确')
    last_end = 0
    for i, cue in enumerate(cues):
        start, end = float(cue['start']), float(cue['end'])
        if not math.isfinite(start + end) or start < 0 or end <= start:
            raise ValueError(f'第 {i + 1} 条字幕的时间不正确')
        if start < last_end - .001:
            raise ValueError(f'第 {i + 1} 条字幕与上一条重叠，请调整时间')
        if not isinstance(cue.get('text'), str) or not cue['text'].strip():
            raise ValueError(f'第 {i + 1} 条字幕内容为空')
        last_end = end
    return cues


def seconds(value):
    h, m, s = value.strip().replace(',', '.').split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def stamp(value, ass=False):
    unit = 100 if ass else 1000
    total = round(float(value) * unit)
    sec, fraction = divmod(total, unit)
    minute, sec = divmod(sec, 60)
    hour, minute = divmod(minute, 60)
    return f'{hour}:{minute:02}:{sec:02}.{fraction:02}' if ass else f'{hour:02}:{minute:02}:{sec:02},{fraction:03}'


def parse_subtitles(text, suffix='.srt'):
    text = text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    cues = []
    if suffix.lower() in ('.ass', '.ssa'):
        fields = []
        active = False
        for line in text.splitlines():
            if line.startswith('['):
                active = line.strip().lower() == '[events]'
            if active and line.lower().startswith('format:'):
                fields = [v.strip().lower() for v in line.split(':', 1)[1].split(',')]
            if active and line.lower().startswith('dialogue:'):
                if not fields or fields[-1] != 'text':
                    raise ValueError('ASS 的 Events Format 必须以 Text 结尾')
                row = dict(zip(fields, line.split(':', 1)[1].strip().split(',', len(fields) - 1)))
                clean = re.sub(r'\{[^}]*\}', '', row['text']).replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ')
                if clean.strip():
                    cues.append(dict(start=seconds(row['start']), end=seconds(row['end']), text=clean))
    else:
        for block in re.split(r'\n\s*\n', text.strip()):
            lines = block.splitlines()
            for index, line in enumerate(lines):
                match = re.match(r'(\d+:\d{2}:\d{2}[,.]\d+)\s*-->\s*(\d+:\d{2}:\d{2}[,.]\d+)', line.strip())
                if match:
                    content = '\n'.join(lines[index + 1:]).strip()
                    if content:
                        cues.append(dict(start=seconds(match[1]), end=seconds(match[2]), text=content))
                    break
    if not cues:
        raise ValueError('没有找到有效字幕，请选择 SRT 或 ASS 文件')
    cues.sort(key=lambda c: c['start'])
    return validate_cues(cues)


def read_subtitles(path):
    data = Path(path).read_bytes()
    for encoding in ('utf-8-sig', 'utf-16', 'gb18030'):
        try:
            return parse_subtitles(data.decode(encoding), Path(path).suffix)
        except UnicodeError:
            continue
    raise ValueError('无法识别字幕文件编码，请转换为 UTF-8')


def to_srt(cues):
    validate_cues(cues)
    return '\n\n'.join(f'{i + 1}\n{stamp(c["start"])} --> {stamp(c["end"])}\n{c["text"]}' for i, c in enumerate(cues)) + '\n'


def to_ass(cues, style, width=1920, height=1080):
    validate_cues(cues)
    style = {**DEFAULT_STYLE, **style}
    color = style['color'].lstrip('#')
    if not re.fullmatch('[0-9a-fA-F]{6}', color):
        raise ValueError('字幕颜色格式不正确')
    color = '&H00' + color[4:6] + color[2:4] + color[0:2]
    font = re.sub(r'[,\r\n]', '', style['font'])
    size = max(8, min(200, float(style['size'])))
    margin = max(0, min(height // 2, int(style['margin'])))
    align = {'bottom': 2, 'center': 5, 'top': 8}.get(style['position'], 2)
    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: {int(width)}
PlayResY: {int(height)}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{color},{color},&H00101010,&H80101010,0,0,0,0,100,100,0,0,{3 if style['background'] else 1},{float(style['outline'])},{float(style['shadow'])},{align},30,30,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    rows = []
    for cue in cues:
        # ASS override sequences must never be interpreted as commands from subtitle text.
        clean = cue['text'].replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\n', '\\N')
        rows.append(f'Dialogue: 0,{stamp(cue["start"], True)},{stamp(cue["end"], True)},Default,,0,0,0,,{clean}')
    return header + '\n'.join(rows) + '\n'


def new_project():
    return dict(version=1, id=uuid.uuid4().hex, name='未命名项目', media=None, cues=[], original_cues=[], style=copy.deepcopy(DEFAULT_STYLE), profile_id='default')


def new_profile(name, identifier=None):
    return dict(id=identifier or uuid.uuid4().hex, name=name, samples=[], stats={}, rules=dict(target_chars=14, max_chars=22, line_chars=18, max_lines=2, pause=.7, keep_punctuation=True, protected_terms=[]))


def flat(text):
    return text.replace('\n', '').replace('\r', '')


def groups(cues, pause):
    result = []
    for cue in cues:
        if not result or cue['start'] - result[-1][-1]['end'] > pause:
            result.append([])
        result[-1].append(cue)
    return result


def learn(profile, cues, name, source_id=None):
    validate_cues(cues)
    if not cues:
        raise ValueError('需要至少一条已校对字幕')
    payload = [dict(start=c['start'], end=c['end'], text=c['text']) for c in cues]
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if any(s['hash'] == digest for s in profile['samples']):
        return profile
    if source_id:
        profile['samples'] = [s for s in profile['samples'] if s.get('source_id') != source_id]
    profile['samples'].append(dict(name=name, hash=digest, source_id=source_id, cues=payload))
    all_cues = [c for s in profile['samples'] for c in s['cues']]
    lengths = sorted(len(flat(c['text']).strip()) for c in all_cues)
    lines = [len(line) for c in all_cues for line in c['text'].splitlines()]
    target = max(2, round(statistics.median(lengths)))
    maximum = max(target, lengths[min(len(lengths) - 1, int(len(lengths) * .9))])
    punctuation = sum(bool(c['text'].rstrip()[-1:] in PUNCT) for c in all_cues) / len(all_cues)
    profile['stats'] = dict(cue_count=len(all_cues), multiline_count=sum('\n' in c['text'] for c in all_cues), median_chars=target, punctuation_ratio=round(punctuation, 2))
    profile['rules'].update(target_chars=target, max_chars=maximum, line_chars=max(2, round(statistics.median(lines))), max_lines=2 if any('\n' in c['text'] for c in all_cues) else 1, keep_punctuation=punctuation >= .3)
    profile['saved_at'] = now()
    return profile


def char_times(cue):
    text = flat(cue['text'])
    words = cue.get('words', [])
    # Edited transcripts invalidate original word alignment unless text still matches.
    if words and ''.join(w['word'] for w in words) == text:
        result = []
        for w in words:
            count = len(w['word'])
            result.extend((w['start'] + (w['end'] - w['start']) * i / count, w['start'] + (w['end'] - w['start']) * (i + 1) / count) for i in range(count))
        return result
    return [(cue['start'] + (cue['end'] - cue['start']) * i / len(text), cue['start'] + (cue['end'] - cue['start']) * (i + 1) / len(text)) for i in range(len(text))]


def boundaries(text, terms):
    allowed = set(range(1, len(text) + 1))
    for match in re.finditer(r'[A-Za-z0-9]+(?:[\x27’_-][A-Za-z0-9]+)*', text):
        allowed.difference_update(range(match.start() + 1, match.end()))
    for term in terms:
        if term:
            for match in re.finditer(re.escape(term), text):
                allowed.difference_update(range(match.start() + 1, match.end()))
    return allowed


def split_offsets(text, rules):
    target, maximum = int(rules['target_chars']), int(rules['max_chars'])
    allowed = boundaries(text, rules.get('protected_terms', []))
    preferred = set()
    try:
        import jieba
        pos = 0
        for token in jieba.cut(text):
            pos += len(token)
            preferred.add(pos)
    except ImportError:
        pass
    cuts, begin = [], 0
    while begin < len(text):
        if len(text) - begin <= maximum:
            cuts.append(len(text))
            break
        options = [i for i in allowed if begin < i <= begin + maximum and text[begin:i].strip()]
        if not options:
            options = [min(i for i in allowed if i > begin)]
        def score(i):
            punctuation = text[i - 1] in PUNCT
            return abs(i - begin - target) - (4 if punctuation else 0) - (2 if i in preferred else 0) + (6 if i < len(text) and text[i] in PUNCT else 0)
        end = min(options, key=score)
        cuts.append(end)
        begin = end
    return cuts


def resegment(cues, profile):
    validate_cues(cues)
    rules = profile['rules']
    memory = {}
    def normalized(text):
        return re.sub('[' + re.escape(PUNCT) + r'\s]', '', simplified_converter().convert(text))
    for sample in profile['samples']:
        for group in groups(sample['cues'], float(rules['pause'])):
            text, cuts = '', []
            for cue in group:
                text += normalized(flat(cue['text']))
                cuts.append(len(text))
            memory[text] = cuts
    result = []
    for group in groups(cues, float(rules['pause'])):
        text = ''.join(flat(c['text']) for c in group)
        timings = [t for c in group for t in char_times(c)]
        key = normalized(text)
        learned = memory.get(key)
        cuts = None
        if learned:
            # Map normalized sample boundaries back onto original characters,
            # retaining punctuation with its preceding phrase and original timing.
            converted = simplified_converter().convert(text)
            if len(converted) == len(text):
                positions = [i for i, char in enumerate(converted) if char not in PUNCT and not char.isspace()]
                cuts = [positions[n] if n < len(positions) else len(text) for n in learned]
        cuts = cuts or split_offsets(text, rules)
        begin = 0
        for end in cuts:
            content = text[begin:end]
            if not rules['keep_punctuation']:
                content = re.sub('[' + re.escape(PUNCT) + ']', '', content)
            if content.strip():
                limit = max(2, int(rules['line_chars']))
                if int(rules['max_lines']) > 1 and len(content) > limit:
                    options = [i for i in boundaries(content, rules.get('protected_terms', [])) if i < len(content)]
                    if options:
                        split = min(options, key=lambda i: abs(i - len(content) / 2))
                        content = content[:split] + '\n' + content[split:]
                start, finish = timings[begin][0], timings[end - 1][1]
                if finish <= start:
                    finish = start + .001
                result.append(dict(start=round(start, 3), end=round(finish, 3), text=content))
            begin = end
    return validate_cues(result)


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def write(self, name, data):
        with self.lock:
            target = self.root / name
            temp = target.with_suffix('.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(target)

    def read(self, name, default):
        path = self.root / name
        with self.lock:
            return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

    def save_project(self, project):
        validate_cues(project['cues'])
        self.write('autosave.json', project)

    def load_project(self):
        return self.read('autosave.json', new_project())

    def profiles(self):
        return self.read('profiles.json', [new_profile('默认习惯', 'default')])

    def record_output(self, path, kind, project_name):
        with self.lock:
            path = str(Path(path).resolve())
            rows = [r for r in self.read('outputs.json', []) if r['path'] != path]
            entry = dict(id=uuid.uuid4().hex, path=path, format=kind, project=project_name, saved_at=now())
            self.write('outputs.json', [entry] + rows[:99])
            return entry
