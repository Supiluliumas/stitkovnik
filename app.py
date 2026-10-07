#!/usr/bin/env python3
"""Local-only camera label reader. Run with python app.py."""
import argparse
import io
import json
import os
import re
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
import zxingcpp
from extractor import DEFAULT_RULES, extract, fold, normalize_macs, validate_rules
from exports import csv_bytes, xlsx_bytes
from ocr import vision_supported, vision_read, tesseract_read, tesseract_binary

ROOT = Path(__file__).resolve().parent
TOKEN = secrets.token_urlsafe(32)
MAX_UPLOAD = 30 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000
OCR_LOCK = threading.Semaphore(2)
register_heif_opener()


def serial_valid(value):
    return bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]{5,59}', value))


def mac_valid(value):
    return bool(re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', value))


def near(left, right):
    if abs(len(left) - len(right)) > 2:
        return False
    row = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        new = [i]
        for j, b in enumerate(right, 1):
            new.append(min(new[-1] + 1, row[j] + 1, row[j - 1] + (a != b)))
        row = new
    return row[-1] <= 2


def barcode_serial(codes, candidates):
    text = '\n'.join(c['text'] for c in candidates)
    tokens = re.findall(r'[A-Za-z0-9]{8,40}', fold(text).upper())
    macs = {c['fields']['MAC'].replace(':', '') for c in candidates if mac_valid(c['fields']['MAC'])}
    matches = set()
    for code in codes:
        value = code['payload'].strip()
        if not re.fullmatch(r'[A-Za-z0-9]{8,40}', value) or value.upper() in macs:
            continue
        if any(near(value.upper(), t) for t in tokens):
            matches.add(value)
    return next(iter(matches)) if len(matches) == 1 else None


def label_crop(image, spans):
    relevant = [s for s in spans if re.search(r'sn|s/n|mac|input|vdc|\bipc|h5a|made in', fold(s['text']))]
    if len(relevant) < 2:
        return None
    left = min(s['left'] for s in relevant)
    top = min(s['top'] for s in relevant)
    right = max(s['left'] + s['width'] for s in relevant)
    bottom = max(s['top'] + s['height'] for s in relevant)
    # Include nearby fragments: a curved MAC line may be split into another
    # observation, and a damaged model heading must not be clipped off.
    surrounding = [s for s in spans if s['top'] + s['height'] >= top - .15 and s['top'] <= bottom + .04
                   and left - .10 <= s['left'] + s['width'] / 2 <= right + .10]
    left = min(s['left'] for s in surrounding)
    top = min(s['top'] for s in surrounding)
    right = max(s['left'] + s['width'] for s in surrounding)
    bottom = max(s['top'] + s['height'] for s in surrounding)
    box = (max(0, int((left - .04) * image.width)), max(0, int((top - .04) * image.height)),
           min(image.width, int((right + .04) * image.width)), min(image.height, int((bottom + .04) * image.height)))
    if (box[2] - box[0]) * (box[3] - box[1]) > image.width * image.height * .9:
        return None
    return image.crop(box)


def ocr_image(data, rules, rotate=True):
    native = vision_supported()
    if not native and not tesseract_binary():
        raise ValueError('Chybí lokální OCR. Nainstalujte Tesseract nebo na Macu nástroje příkazem xcode-select --install.')
    with Image.open(io.BytesIO(data)) as source:
        if source.width * source.height > Image.MAX_IMAGE_PIXELS:
            raise ValueError("Obrázek přesahuje 40 megapixelů. Zmenšete jej nebo ořízněte na štítek.")
        image = ImageOps.exif_transpose(source).convert("RGB")
    if image.width < 30 or image.height < 30:
        raise ValueError("Obrázek je příliš malý pro čtení štítku.")
    # Preserve the original pixels for Vision; never shrink high-quality label text.
    codes = [{'payload': c.text, 'symbology': str(c.format)} for c in zxingcpp.read_barcodes(image)]
    candidates, failures = [], []
    crop = None

    def add(text, confidence, engine, angle, priority):
        result = extract(text, rules)
        candidates.append({**result, 'confidence': confidence, 'rotation': angle, 'engine': engine, 'priority': priority})

    def complete():
        serial = barcode_serial(codes, candidates)
        return any((serial or serial_valid(c['fields']['S/N'])) and mac_valid(c['fields']['MAC']) and c['confidence'] >= 85 for c in candidates)

    with tempfile.TemporaryDirectory(prefix="stitky-") as folder:
        path = Path(folder) / 'label.png'
        if native:
            try:
                image.save(path)
                text, confidence, native_codes, spans = vision_read(path, True)
                codes.extend(native_codes)
                add(text, confidence, 'Apple Vision', 0, 20)
                crop = label_crop(image, spans)
                if crop is not None:
                    crop.save(path)
                    text, confidence, native_codes = vision_read(path)
                    codes.extend(native_codes)
                    add(text, confidence, 'Apple Vision · výřez štítku', 0, 30)
                if not complete() and crop is not None:
                    crop.resize((crop.width * 3, crop.height * 3), Image.Resampling.BICUBIC).save(path)
                    text, confidence, native_codes = vision_read(path)
                    codes.extend(native_codes)
                    add(text, confidence, 'Apple Vision · zvětšený výřez', 0, 25)
                if rotate and not complete():
                    for angle in (90, 180, 270):
                        image.rotate(angle, expand=True, fillcolor='white').save(path)
                        text, confidence, native_codes = vision_read(path)
                        codes.extend(native_codes)
                        add(text, confidence, 'Apple Vision', angle, 20)
                        if complete():
                            break
            except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                failures.append(str(error))
        if not complete() and tesseract_binary():
            base = crop if crop is not None else image
            prepared = ImageOps.autocontrast(ImageOps.grayscale(base), cutoff=.5)
            if max(prepared.size) < 2500:
                prepared = prepared.resize((prepared.width * 2, prepared.height * 2), Image.Resampling.LANCZOS)
            for angle, psm in [(0, 6), (0, 11)] + ([(90, 6), (180, 6), (270, 6)] if rotate else []):
                try:
                    oriented = prepared.rotate(angle, expand=True, fillcolor=255)
                    oriented.save(path)
                    text, confidence, spans = tesseract_read(path, psm, include_spans=True)
                    add(text, confidence, f'Tesseract · režim {psm}', angle, 10)
                    if not complete():
                        focused = label_crop(oriented, spans)
                        if focused is not None:
                            # Enlarge the label independently of the full photo;
                            # a small label in a large photo previously stayed tiny.
                            scale = min(3, 6000 / max(focused.size))
                            if scale > 1:
                                focused = focused.resize((round(focused.width * scale), round(focused.height * scale)), Image.Resampling.LANCZOS)
                            focused = ImageOps.expand(focused, border=12, fill=255)
                            codes.extend({'payload': c.text, 'symbology': str(c.format)} for c in zxingcpp.read_barcodes(focused))
                            skew = spans[0].get('skew', 0) if spans else 0
                            variants = [(focused, 'výřez štítku')]
                            if skew:
                                variants.insert(0, (focused.rotate(skew, expand=True, fillcolor=255), 'narovnaný výřez štítku'))
                            for variant, description in variants:
                                variant.save(path)
                                for crop_psm in (6, 11):
                                    text, confidence = tesseract_read(path, crop_psm)
                                    add(text, confidence, f'Tesseract · {description} · režim {crop_psm}', angle, 10)
                                    if complete():
                                        break
                                if complete():
                                    break
                    if complete():
                        break
                except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                    failures.append(str(error))
    if not candidates:
        raise ValueError('Zpracování OCR selhalo. ' + '; '.join(failures))
    def score(c):
        return (serial_valid(c['fields']['S/N']) + mac_valid(c['fields']['MAC'])) * 1000 + c['priority'] * 10 + c['confidence']
    best = max(candidates, key=score)
    result = {**best, 'fields': dict(best['fields']), 'ocrWarnings': [], 'sources': {}}
    del result['priority']
    for key, validator in [('S/N', serial_valid), ('MAC', mac_valid)]:
        valid = [c for c in candidates if validator(c['fields'][key])]
        if valid:
            chosen = max(valid, key=lambda c: (serial_valid(c['fields']['S/N']) and mac_valid(c['fields']['MAC']), c['priority'], c['confidence']))
            result['fields'][key] = chosen['fields'][key]
            result['sources'][key] = chosen['engine']
        if len({c['fields'][key] for c in valid if c['confidence'] >= 75}) > 1:
            result['ocrWarnings'].append(f'Různá čtení {key} – ověřte podle štítku')
    serial = barcode_serial(codes, candidates)
    if serial:
        result['fields']['S/N'] = serial
        result['sources']['S/N'] = 'Čárový / QR kód, přiřazený k vytištěnému číslu'
        result['ocrWarnings'] = [w for w in result['ocrWarnings'] if 'S/N' not in w]
    # Retain the original full OCR alongside the cropped pass, for all other label text.
    result['text'] = best['text']
    result['originalText'] = candidates[0]['text']
    result['readings'] = [{k: c[k] for k in ('text', 'fields', 'engine', 'confidence')} for c in candidates]
    result['barcodes'] = list({(c['payload'], c['symbology']): c for c in codes}.values())
    result['warnings'] = extract('', rules)['warnings'] if not result['text'] else []
    if not serial_valid(result['fields']['S/N']):
        result['ocrWarnings'].append('S/N chybí nebo má podezřelý formát')
    if not mac_valid(result['fields']['MAC']):
        result['ocrWarnings'].append('MAC chybí nebo má neplatný formát')
    if result['confidence'] < 75:
        result['ocrWarnings'].append('Nižší jistota OCR – ověřte podle obrázku')
    return result


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type="application/json; charset=utf-8", filename=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {"error": "Neplatná adresa aplikace."})
        path = urlparse(self.path).path
        if path == "/api/config":
            return self.send(200, {"rules": DEFAULT_RULES, "token": TOKEN, "ocr": vision_supported() or bool(tesseract_binary()), 'engine': 'Apple Vision + čtení kódů' if vision_supported() else 'Tesseract + čtení kódů'})
        files = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
        if path not in files:
            return self.send(404, {"error": "Nenalezeno"})
        name, mime = files[path]
        self.send(200, (ROOT / "static" / name).read_bytes(), mime)

    def do_POST(self):
        if not self.valid_host() or self.headers.get("X-App-Token") != TOKEN:
            return self.send(403, {"error": "Obnovte stránku aplikace."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > MAX_UPLOAD:
                return self.send(413, {"error": "Soubor je prázdný nebo přesahuje 30 MB."})
            data = self.rfile.read(size)
            path = urlparse(self.path).path
            if path == "/api/scan":
                rules = validate_rules(json.loads(self.headers.get("X-Rules", "{}")))
                with OCR_LOCK:
                    result = ocr_image(data, rules, self.headers.get("X-Rotate", "true") == "true")
                return self.send(200, result)
            payload = json.loads(data)
            if not isinstance(payload, dict):
                raise ValueError("Neplatný požadavek.")
            if path == "/api/reparse":
                return self.send(200, extract(str(payload.get("text", "")), validate_rules(payload.get("rules"))))
            if path in ("/api/export/xlsx", "/api/export/csv"):
                rows = payload.get("rows", [])
                if not isinstance(rows, list) or not rows or len(rows) > 10000:
                    raise ValueError("Export musí obsahovat 1 až 10 000 řádků.")
                if any(not isinstance(r, dict) or not isinstance(r.get("fields", {}), dict) for r in rows):
                    raise ValueError("Neplatné řádky exportu.")
                xlsx = path.endswith("xlsx")
                return self.send(200, xlsx_bytes(rows) if xlsx else csv_bytes(rows),
                                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if xlsx else "text/csv; charset=utf-8",
                                 "stitky-kamer." + ("xlsx" if xlsx else "csv"))
            return self.send(404, {"error": "Nenalezeno"})
        except (UnidentifiedImageError, Image.DecompressionBombError):
            self.send(400, {"error": "Obrázek je neplatný nebo příliš velký. Použijte JPG, PNG, TIFF, BMP, WebP nebo HEIC."})
        except subprocess.TimeoutExpired:
            self.send(408, {"error": "Čtení trvalo příliš dlouho. Zkuste oříznout fotografii na samotný štítek."})
        except (ValueError, TypeError, KeyError, OSError) as error:
            self.send(400, {"error": str(error)})

    def log_message(self, format, *args):
        if args and str(args[1]) not in ("200", "404"):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description="Lokální čtečka štítků kamer")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"\nŠtítkovník běží na {url}\nZastavení: Ctrl+C\n", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
