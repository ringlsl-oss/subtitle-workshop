"""Record the current interpreter for a local desktop build. Never commit runtime.json."""
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
settings = {'python': str(Path(sys.executable).resolve()), 'site_packages': []}
(root / 'runtime.json').write_text(json.dumps(settings, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print('Created local runtime.json for the current Python environment.')
