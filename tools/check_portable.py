#!/usr/bin/env python3
"""Exercise the distributed ZIP with no external commands on the app's PATH."""
import io
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zipfile import ZipFile


def main():
    archive = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='Štítkovník test ') as folder:
        windows = sys.platform == 'win32'
        if windows:
            with ZipFile(archive) as zipped:
                zipped.extractall(folder)
            package = Path(folder) / 'Stitkovnik-Windows-x64'
            command = [os.environ.get('COMSPEC', r'C:\Windows\System32\cmd.exe'),
                       '/d', '/c', str(package / 'Spustit.bat')]
        else:
            subprocess.run(['/usr/bin/ditto', '-x', '-k', str(archive), folder], check=True)
            package = next(Path(folder).glob('Stitkovnik-macOS-*'))
            command = [str(package / 'Spustit.command')]
        process = subprocess.Popen([*command, '--port', '0', '--no-browser'],
                                   cwd=folder, env={**os.environ, 'PATH': folder},
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        lines = queue.Queue()

        def read_output():
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        threading.Thread(target=read_output, daemon=True).start()
        try:
            while True:
                line = lines.get(timeout=45)
                if line is None:
                    raise RuntimeError('Přenosný nástroj se ukončil před spuštěním serveru.')
                match = re.search(r'http://127\.0\.0\.1:\d+', line)
                if match:
                    url = match.group()
                    break

            def request(path, data=None, headers=None):
                try:
                    with urlopen(Request(url + path, data=data, headers=headers or {}), timeout=90) as response:
                        return response.read()
                except HTTPError as error:
                    raise RuntimeError(error.read().decode('utf-8')) from error

            config = json.loads(request('/api/config'))
            engine = 'Tesseract' if windows else 'Apple Vision'
            assert config['ocr'] and engine in config['engine'], config
            assert b'<html' in request('/').lower()
            for resource in ('/app.js', '/style.css'):
                assert request(resource)
            headers = {'X-App-Token': config['token'], 'X-Rules': json.dumps(config['rules'], ensure_ascii=True)}
            rows = []
            expected = [('kamera-01.png', '000123456789', 'A4:14:37:00:12:AB'),
                        ('kamera-02-otocena.png', '000987654321', '00:11:22:33:44:55')]
            for filename, serial, mac in expected:
                result = json.loads(request('/api/scan', (package / 'ukazkove-stitky' / filename).read_bytes(), headers))
                assert result['fields']['S/N'] == serial, result
                assert result['fields']['MAC'] == mac, result
                assert engine in result['engine'], result
                rows.append({'filename': filename, **result})
                print(f'OK: {filename}, S/N {serial}, MAC {mac}', flush=True)
            payload = json.dumps({'rows': rows}).encode()
            for extension in ('xlsx', 'csv'):
                exported = request('/api/export/' + extension, payload, headers)
                if extension == 'xlsx':
                    with ZipFile(io.BytesIO(exported)) as book:
                        sheet = book.read('xl/worksheets/sheet1.xml')
                        assert all(serial.encode() in sheet for _, serial, _ in expected)
                else:
                    assert all(serial in exported.decode('utf-8-sig') for _, serial, _ in expected)
                print(f'OK: export {extension}', flush=True)
            print('OK: ZIP běží mimo projekt, z cesty s mezerami a diakritikou, bez Pythonu / swiftc / Tesseractu v PATH.')
        finally:
            if windows:
                if process.poll() is None:
                    taskkill = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'taskkill.exe'
                    subprocess.run([str(taskkill), '/pid', str(process.pid), '/t', '/f'], capture_output=True, timeout=10)
            else:
                process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
