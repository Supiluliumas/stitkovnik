#!/usr/bin/env python3
"""Assemble a Windows x64 ZIP on any host, using official embeddable Python."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile
from check_windows_archive import check

ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = '3.13.16'
DOWNLOADS = {
    'python-3.13.16-embed-amd64.zip': (
        'https://www.python.org/ftp/python/3.13.16/python-3.13.16-embed-amd64.zip',
        '97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297'),
    'tesseract-setup.exe': (
        'https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe',
        'f3fc4236425b690c8be756f35793f77394ee004be0a6460a440c754d892f68bc'),
    'eng.traineddata': (
        'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/eng.traineddata',
        '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'),
    'tessdata-LICENSE': (
        'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/LICENSE',
        'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'),
    'vc_redist.x64.exe': (
        'https://download.visualstudio.microsoft.com/download/pr/ebdab8e5-1d7b-4d9f-a11b-cbb1720c3b12/843068991DAAA1F73AD9F6239BCE4D0F6A07A51F18C37EA2A867E9BECA71295C/VC_redist.x64.exe',
        '843068991daaa1f73ad9f6239bce4d0f6a07a51f18c37ea2a867e9beca71295c'),
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def download(path, url, sha256):
    if path.is_file() and digest(path) == sha256:
        return
    temporary = path.with_suffix('.download')
    with urlopen(url, timeout=90) as response, temporary.open('wb') as output:
        shutil.copyfileobj(response, output)
    if digest(temporary) != sha256:
        temporary.unlink()
        raise ValueError(f'Nesouhlasí SHA-256: {path.name}')
    temporary.replace(path)


def extract_vc_runtime(cache, sevenzip):
    # WiX Burn embeds two CABs; 7-Zip exposes only the bootstrapper's first CAB.
    # Carve the signed, checksum-verified distribution's CABs without executing it.
    data = (cache / 'vc_redist.x64.exe').read_bytes()
    start, cabinets = 0, []
    while True:
        offset = data.find(b'MSCF', start)
        if offset < 0:
            break
        size = struct.unpack_from('<I', data, offset + 8)[0]
        if data[offset + 4:offset + 8] == b'\0' * 4 and 36 <= size <= len(data) - offset:
            cabinet = cache / f'vc-cab-{len(cabinets)}.cab'
            cabinet.write_bytes(data[offset:offset + size])
            cabinets.append(cabinet)
            start = offset + size
        else:
            start = offset + 4
    if len(cabinets) != 2:
        raise ValueError('Neočekávaná struktura Microsoft C++ runtime.')
    payload = cache / 'vc-payload'
    run(sevenzip, 'x', '-y', f'-o{payload}', cabinets[1])
    libraries = cache / 'vc-dll'
    # a4 is the x64 minimum-runtime CAB in this pinned release (14.51.36247).
    run(sevenzip, 'x', '-y', f'-o{libraries}', payload / 'a4')
    if not (libraries / 'msvcp140.dll_amd64').is_file():
        raise ValueError('Chybí Microsoft C++ runtime pro ZXing.')
    license_file = cache / 'VC-LICENSE.html'
    if not license_file.is_file():
        with urlopen('https://aka.ms/VCRedistLicense', timeout=90) as response, license_file.open('wb') as output:
            shutil.copyfileobj(response, output)
    return libraries, license_file


def main():
    parser = argparse.ArgumentParser(description='Přenosný Štítkovník pro Windows 10/11 x64')
    parser.add_argument('--sevenzip', default=shutil.which('7zz') or shutil.which('7z'), help='Cesta k 7zz nebo 7z pro rozbalení OCR instalátoru (instalátor se nespouští).')
    args = parser.parse_args()
    if not args.sevenzip:
        parser.error('Pro sestavení potřebujete 7-Zip; předejte --sevenzip /cesta/k/7zz.')
    cache = ROOT / '.build' / 'windows'
    cache.mkdir(parents=True, exist_ok=True)
    for name, (url, sha256) in DOWNLOADS.items():
        download(cache / name, url, sha256)
    vc_libraries, vc_license = extract_vc_runtime(cache, args.sevenzip)
    wheels = cache / 'wheels'
    run(sys.executable, '-m', 'pip', 'download', '--only-binary=:all:', '--platform', 'win_amd64',
        '--python-version', '3.13', '--implementation', 'cp', '--abi', 'cp313', '--dest', wheels,
        '-r', ROOT / 'requirements-windows-portable.txt')
    extracted = cache / 'tesseract-extracted'
    run(args.sevenzip, 'x', '-y', f'-o{extracted}', cache / 'tesseract-setup.exe')
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    # Always assemble from a clean staging folder; never include working data.
    name = 'Stitkovnik-Windows-x64'
    with tempfile.TemporaryDirectory(prefix='windows-package-', dir=cache) as staging:
        package = Path(staging) / name
        runtime = package / 'runtime'
        runtime.mkdir(parents=True)
        with ZipFile(cache / 'python-3.13.16-embed-amd64.zip') as archive:
            archive.extractall(runtime)
        for library in vc_libraries.glob('*.dll_amd64'):
            shutil.copyfile(library, runtime / library.name.removesuffix('_amd64'))
        (runtime / 'python313._pth').write_text('python313.zip\n.\n..\nLib/site-packages\nimport site\n', encoding='ascii')
        site = runtime / 'Lib' / 'site-packages'
        run(sys.executable, '-m', 'pip', 'install', '--no-compile', '--only-binary=:all:',
            '--platform', 'win_amd64', '--python-version', '3.13', '--implementation', 'cp', '--abi', 'cp313',
            '--no-index', '--find-links', wheels, '--target', site,
            '-r', ROOT / 'requirements-windows-portable.txt')
        for source in ('app.py', 'ocr.py', 'extractor.py', 'exports.py'):
            shutil.copyfile(ROOT / source, package / source)
        for folder in ('static', 'ukazkove-stitky'):
            shutil.copytree(ROOT / folder, package / folder,
                            ignore=shutil.ignore_patterns('.DS_Store', '__pycache__'))
        native = package / 'native' / 'tesseract'
        native.mkdir(parents=True)
        shutil.copyfile(extracted / 'tesseract.exe', native / 'tesseract.exe')
        for library in extracted.glob('*.dll'):
            shutil.copyfile(library, native / library.name)
        shutil.copytree(extracted / 'tessdata', native / 'tessdata')
        shutil.copyfile(cache / 'eng.traineddata', native / 'tessdata' / 'eng.traineddata')
        shutil.copytree(extracted / 'doc', native / 'doc')
        if not (native / 'tessdata' / 'eng.traineddata').is_file():
            raise ValueError('V OCR balíčku chybí model eng.')
        (package / 'Spustit.bat').write_bytes(b'''@echo off\r
setlocal\r
cd /d "%~dp0"\r
"%~dp0runtime\\python.exe" -B -X utf8 "%~dp0app.py" %*\r
if errorlevel 1 (\r
  echo Spusteni se nezdarilo. Podrobnosti jsou uvedene vyse.\r
  pause\r
)\r
endlocal\r
''')
        (package / 'CTI-ME.txt').write_text('''ŠTÍTKOVNÍK – PŘENOSNÁ VERZE PRO WINDOWS

Určeno pro Windows 10 / 11, 64bitový procesor Intel nebo AMD (x64).

1. Rozbalte celý ZIP do vlastní složky. Nespouštějte soubory přímo uvnitř ZIPu.
2. Dvakrát klikněte na Spustit.bat.
3. Otevře se příkazové okno a aplikace v běžném prohlížeči.
4. Načtěte fotografie nebo složku ukazkove-stitky a exportujte výsledky do Excelu.
5. Příkazové okno nechte při práci otevřené. Ukončení: Ctrl+C v tomto okně.

Python ani Tesseract nemusíte instalovat. Nepotřebujete oprávnění správce.
Spuštění a zpracování fotografií fungují bez internetu; fotografie se nikam
neodesílají. OCR používá Tesseract, proto se čtení může lišit od verze pro Mac.

Tabulka a pravidla se ukládají do úložiště vašeho prohlížeče pro adresu a port
aplikace, nikoli do tohoto balíčku. Při přenosu ZIPu se výsledky nepřenášejí.
Před ukončením práce exportujte Excel nebo CSV. Fotografie se neuchovávají.
Adresa aplikace je uvedená v příkazovém okně; výchozí port je 8765.

Balíček byl sestaven na Macu z Windows distribucí Pythonu a knihoven.
Ověření přímo na Windows je potřeba provést před širším nasazením.
Podrobný návod je v NAVOD.md. Sdílejte celý ZIP včetně runtime a native.
''', encoding='utf-8-sig')
        shutil.copyfile(ROOT / 'README.md', package / 'NAVOD.md')
        licenses = package / 'licence'
        licenses.mkdir()
        shutil.copyfile(runtime / 'LICENSE.txt', licenses / 'Python-LICENSE.txt')
        for info in site.glob('*.dist-info'):
            for source in info.rglob('*'):
                if source.is_file() and any(word in str(source.relative_to(info)).lower() for word in ('license', 'copying', 'notice')):
                    target = licenses / info.name / source.relative_to(info)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
        shutil.copytree(extracted / 'doc', licenses / 'tesseract')
        shutil.copyfile(cache / 'tessdata-LICENSE', licenses / 'tessdata-LICENSE')
        shutil.copyfile(vc_license, licenses / 'Microsoft-VC-LICENSE.html')
        manifest = {
            'platform': 'Windows x64', 'python': PYTHON_VERSION,
            'ocr': 'Tesseract 5.5.0.20241111',
            'vc_runtime': 'Microsoft Visual C++ 14.51.36247 (x64, app-local)',
            'downloads': [{'file': n, 'url': u, 'sha256': h} for n, (u, h) in DOWNLOADS.items()],
            'wheels': [{'file': f.name, 'sha256': digest(f)} for f in sorted(wheels.glob('*.whl'))],
        }
        (licenses / 'ZDROJE.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        archive = Path(shutil.make_archive(str(dist / name), 'zip', root_dir=staging, base_dir=name))
    check(archive)
    archive.with_suffix('.zip.sha256').write_text(f'{digest(archive)}  {archive.name}\n', encoding='ascii')
    print(f'\nHotovo: {archive} ({archive.stat().st_size / 1024**2:.1f} MB)', flush=True)


if __name__ == '__main__':
    main()
