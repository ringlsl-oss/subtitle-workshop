"""Isolated recognition process: cancellation does not leave a model running."""
import json
import os
from pathlib import Path
import sys


def configure_runtime():
    """Use physical dependency paths, including when launched outside MSIX."""
    import site
    root = Path(__file__).resolve().parent
    config = root / 'runtime.json'
    settings = json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
    for location in settings.get('site_packages', []):
        path = Path(location)
        if not path.is_absolute():
            path = root / path
        if not path.is_dir():
            raise RuntimeError('语音识别依赖目录不存在，请修复识别环境：' + str(path))
        site.addsitedir(str(path))
    # Whisper invokes ffmpeg by name. Explorer may have a different PATH.
    if (root / 'bin' / 'ffmpeg.exe').is_file():
        os.environ['PATH'] = str(root / 'bin') + os.pathsep + os.environ.get('PATH', '')
    if settings.get('models'):
        settings['models'] = str((root / settings['models']).resolve())
    return settings


def main():
    settings = configure_runtime()
    import torch
    import whisper
    data = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    torch.set_num_threads(max(1, min(8, (os.cpu_count() or 4) // 2)))
    model = whisper.load_model(data.get('model', 'small'), device='cpu', download_root=settings.get('models'))
    print('PROGRESS ' + json.dumps(dict(progress=10, message='模型已加载，正在识别语音…（CPU 识别需要一些时间）'), ensure_ascii=False), flush=True)
    result = model.transcribe(data['path'], language=data.get('language') or None, word_timestamps=True, fp16=False, verbose=False, initial_prompt=data.get('prompt') or None, condition_on_previous_text=False)
    cues = []
    last_end = 0
    for segment in result['segments']:
        text = segment['text'].strip()
        start = max(last_end, float(segment['start']))
        end = float(segment['end'])
        if text and end > start:
            words = [dict(word=w['word'], start=w['start'], end=w['end']) for w in segment.get('words', [])]
            # Whisper often prefixes a space; retain exact character alignment.
            if words:
                words[0]['word'] = words[0]['word'].lstrip()
                words[-1]['word'] = words[-1]['word'].rstrip()
            cues.append(dict(start=start, end=end, text=text, words=words))
            last_end = end
    if not cues:
        raise ValueError('未识别到有效语音，请检查音轨或更换语言设置')
    Path(sys.argv[2]).write_text(json.dumps(cues, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
