#!/usr/bin/env python3
"""Build a self-contained macOS ZIP; run using requirements-build.txt."""
import hashlib
import importlib.metadata
import platform
import re
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def main():
    if sys.platform != 'darwin':
        raise SystemExit('Tento build je určený pro macOS. Sestavujte na cílovém systému.')
    arch = platform.machine()
    if arch not in ('arm64', 'x86_64'):
        raise SystemExit(f'Nepodporovaná architektura: {arch}')
    # Homebrew runtimes can require the host OS and defeat portability.
    library = next(Path(sys.base_prefix).rglob(f'libpython{sys.version_info.major}.{sys.version_info.minor}.dylib'), None)
    if library is None:
        library = Path(sys.base_prefix) / 'Python'
    if library.is_file():
        info = subprocess.check_output(['otool', '-l', str(library)], text=True)
        minimums = re.findall(r'\bminos (\d+)\.(\d+)', info)
        if any(tuple(map(int, version)) > (13, 0) for version in minimums):
            raise SystemExit('Tento Python vyžaduje novější macOS než 13. Použijte přenositelný Python, například z uv.')
    work = ROOT / '.build' / 'portable' / arch
    work.mkdir(parents=True, exist_ok=True)
    vision = work / 'label-vision'
    run('swiftc', '-O', '-target', f'{arch}-apple-macos13.0', ROOT / 'native' / 'vision.swift', '-o', vision)
    name = f'Stitkovnik-macOS-{arch}'
    package = ROOT / 'dist' / name
    package.mkdir(parents=True, exist_ok=True)
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
        '--console', '--name', 'Stitkovnik', '--target-arch', arch,
        '--distpath', package, '--workpath', work / 'pyinstaller', '--specpath', work,
        '--add-data', f'{ROOT / "static"}:static',
        '--add-binary', f'{vision}:native',
        '--collect-all', 'pillow_heif', '--collect-all', 'zxingcpp',
        '--exclude-module', 'playwright', '--exclude-module', 'openpyxl',
        ROOT / 'app.py')
    launcher = package / 'Spustit.command'
    launcher.write_text('''#!/bin/zsh
cd "${0:A:h}" || exit 1
exec ./Stitkovnik "$@"
''', encoding='utf-8')
    launcher.chmod(0o755)
    shutil.copytree(ROOT / 'ukazkove-stitky', package / 'ukazkove-stitky', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('.DS_Store', '__pycache__'))
    label = 'Apple Silicon (M1 a novější)' if arch == 'arm64' else 'Intel'
    (package / 'CTI-ME.txt').write_text(f'''ŠTÍTKOVNÍK – PŘENOSNÁ VERZE PRO MAC

Určeno pro: macOS 13 a novější, {label}.
Balíček je ověřený na systému použitém při sestavení; starší macOS je nutné ověřit samostatně.

1. Rozbalte celý ZIP do vlastní složky.
2. Dvakrát klikněte na Spustit.command.
3. Otevře se Terminál a aplikace v prohlížeči.
4. Vyberte fotografie nebo vyzkoušejte složku ukazkove-stitky.
5. Výsledek exportujte do Excelu. Aplikaci ukončíte Ctrl+C v Terminálu.

Python, Homebrew, Xcode ani Tesseract nemusíte instalovat.
Internet není potřeba. Fotografie se zpracovávají pouze na vašem Macu.
Nejprve může chvíli trvat rozbalení vestavěného prostředí do dočasné složky.

Balíček nemá podpis Developer ID ani notarizaci od Apple. Pokud macOS spuštění
zablokuje, po pokusu o spuštění otevřete Nastavení systému > Soukromí a zabezpečení
a povolte otevření tohoto nástroje, pokud důvěřujete jeho odesílateli.

Tabulka a pravidla jsou uložené v použitém prohlížeči pro danou adresu a port,
ne ve složce tohoto balíčku. Nepřenášejí se spolu s nástrojem. Fotografie se
do úložiště prohlížeče neukládají. Před ukončením práce exportujte výsledky.
Při obsazeném portu 8765 aplikace zvolí jiný; ten má vlastní úložiště.

Podrobný návod je v NAVOD.md. Sdílejte celý ZIP.
''', encoding='utf-8')
    shutil.copyfile(ROOT / 'README.md', package / 'NAVOD.md')
    licenses = package / 'licence'
    licenses.mkdir(exist_ok=True)
    notices = ['Štítkovník obsahuje následující knihovny a běhové prostředí.\n']
    for dependency in ('pillow', 'pillow-heif', 'zxing-cpp', 'pyinstaller'):
        distribution = importlib.metadata.distribution(dependency)
        notices.append(f'{dependency} {distribution.version}')
        for entry in distribution.files or []:
            if any(word in str(entry).lower() for word in ('license', 'licence', 'copying', 'notice')):
                source = Path(distribution.locate_file(entry))
                if source.is_file():
                    target = licenses / dependency / Path(str(entry))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    python_license = Path(sys.base_prefix) / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'LICENSE.txt'
    if not python_license.is_file():
        raise SystemExit(f'Chybí licence Pythonu: {python_license}')
    shutil.copyfile(python_license, licenses / 'Python-LICENSE.txt')
    notices.append(f'Python {platform.python_version()}')
    (licenses / 'PREHLED.txt').write_text('\n'.join(notices) + '\n', encoding='utf-8')
    archive = ROOT / 'dist' / f'{name}.zip'
    if archive.exists():
        archive.unlink()
    run('ditto', '-c', '-k', '--keepParent', package, archive)
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(f'\nHotovo: {archive} ({archive.stat().st_size / 1024**2:.1f} MB)', flush=True)


if __name__ == '__main__':
    main()
