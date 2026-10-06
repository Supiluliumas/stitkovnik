"""Local OCR engines and position-aware reconstruction of label rows."""
import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parent
BUILD_LOCK = threading.Lock()


def bundled_vision():
    return ROOT / 'native' / 'label-vision'


def vision_supported():
    return sys.platform == 'darwin' and (bundled_vision().is_file() or bool(shutil.which('swiftc')))


def vision_binary():
    if bundled_vision().is_file():
        return bundled_vision()
    if getattr(sys, 'frozen', False):
        raise ValueError('V přenosném balíčku chybí pomocný program Apple Vision. Rozbalte celý balíček znovu.')
    source = ROOT / 'native' / 'vision.swift'
    target = ROOT / '.build' / 'label-vision'
    with BUILD_LOCK:
        if not target.exists() or target.stat().st_mtime < source.stat().st_mtime:
            target.parent.mkdir(exist_ok=True)
            temporary = target.with_suffix('.tmp')
            process = subprocess.run(['swiftc', '-O', str(source), '-o', str(temporary)], capture_output=True, text=True, timeout=120)
            if process.returncode:
                raise ValueError('Apple Vision se nepodařilo připravit. ' + process.stderr[-500:])
            temporary.replace(target)
    return target


def reconstruct(spans):
    """Merge label/value fragments by position, even across OCR blocks."""
    groups = []
    for span in sorted(spans, key=lambda s: (s['top'] + s['height'] / 2, s['left'])):
        middle = span['top'] + span['height'] / 2
        compatible = [g for g in groups if abs(g['middle'] - middle) <= min(g['height'], span['height']) * 0.45]
        if compatible:
            group = min(compatible, key=lambda g: abs(g['middle'] - middle))
            group['spans'].append(span)
            group['middle'] = sum(s['top'] + s['height'] / 2 for s in group['spans']) / len(group['spans'])
            group['height'] = min(group['height'], span['height'])
        else:
            groups.append({'middle': middle, 'height': span['height'], 'spans': [span]})
    text = '\n'.join(' '.join(s['text'] for s in sorted(g['spans'], key=lambda s: s['left'])) for g in sorted(groups, key=lambda g: g['middle']))
    # Weight line observations and individual words by their character count.
    count = sum(len(s['text']) for s in spans)
    confidence = round(sum(s['confidence'] * len(s['text']) for s in spans) / count) if count else 0
    return text, confidence


def vision_read(path, include_spans=False):
    result = subprocess.run([str(vision_binary()), str(path)], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError('Apple Vision nemohlo přečíst obrázek: ' + result.stderr[-300:])
    output = json.loads(result.stdout)
    text, confidence = reconstruct(output['spans'])
    result = (text, confidence, output['barcodes'])
    return (*result, output['spans']) if include_spans else result


def tesseract_binary():
    bundled = ROOT / 'native' / 'tesseract' / 'tesseract.exe'
    if sys.platform == 'win32' and bundled.is_file():
        return str(bundled)
    return shutil.which('tesseract')


def tesseract_read(path, psm):
    binary = tesseract_binary()
    if not binary:
        raise ValueError('Chybí lokální OCR Tesseract. Rozbalte celý přenosný balíček nebo nainstalujte Tesseract.')
    environment = {**os.environ, 'OMP_THREAD_LIMIT': '2'}
    working_directory = None
    if Path(binary).parent == ROOT / 'native' / 'tesseract':
        # MinGW Tesseract cannot reliably open Unicode paths. CreateProcessW
        # sets the Unicode working directory; Tesseract sees only relative ASCII
        # model paths and receives image bytes through stdin.
        working_directory = Path(binary).parent
        environment['TESSDATA_PREFIX'] = 'tessdata'
    result = subprocess.run([binary, 'stdin', 'stdout', '-l', 'eng', '--psm', str(psm), 'tsv'],
                            input=Path(path).read_bytes(), capture_output=True, timeout=60,
                            cwd=working_directory, env=environment,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        details = result.stderr.decode('utf-8', errors='replace')[-600:]
        raise ValueError(f'Tesseract nemohlo obrázek přečíst (kód {result.returncode}). Ověřte instalaci a jazyk eng. ' + details)
    spans = []
    for word in csv.DictReader(io.StringIO(result.stdout.decode('utf-8', errors='replace')), delimiter='\t', quoting=csv.QUOTE_NONE):
        content = word.get('text', '').strip()
        if content and word.get('level') == '5':
            spans.append({'text': content, 'confidence': float(word['conf']),
                          **{k: float(word[k]) for k in ('left', 'top', 'width', 'height')}})
    return reconstruct(spans)
