#!/usr/bin/env python3
"""Check x64 PE architecture and DLL dependencies without running Windows code."""
from pathlib import Path
import struct
import sys
from zipfile import ZipFile

SYSTEM_DLLS = set('''kernel32.dll user32.dll gdi32.dll advapi32.dll shell32.dll ole32.dll
oleaut32.dll ws2_32.dll ntdll.dll ucrtbase.dll msvcrt.dll version.dll crypt32.dll bcrypt.dll
rpcrt4.dll shlwapi.dll secur32.dll normaliz.dll winmm.dll comdlg32.dll comctl32.dll netapi32.dll
userenv.dll psapi.dll dnsapi.dll iphlpapi.dll dbghelp.dll mpr.dll powrprof.dll wldap32.dll
setupapi.dll propsys.dll dwmapi.dll winspool.drv imm32.dll opengl32.dll dwrite.dll d2d1.dll
d3d11.dll dxgi.dll dxva2.dll mfplat.dll mf.dll mfreadwrite.dll avrt.dll authz.dll wtsapi32.dll
hid.dll winhttp.dll cfgmgr32.dll usp10.dll msimg32.dll d3dcompiler_47.dll'''.split())


def imports(data):
    pe = struct.unpack_from('<I', data, 60)[0]
    if data[pe:pe + 4] != b'PE\0\0' or struct.unpack_from('<H', data, pe + 4)[0] != 0x8664:
        raise ValueError('Balíček obsahuje binární soubor, který není Windows x64.')
    count = struct.unpack_from('<H', data, pe + 6)[0]
    size = struct.unpack_from('<H', data, pe + 20)[0]
    optional = pe + 24
    if struct.unpack_from('<H', data, optional)[0] != 0x20b:
        raise ValueError('Neočekávaný PE formát.')
    sections = [struct.unpack_from('<IIII', data, optional + size + i * 40 + 8) for i in range(count)]

    def address(rva):
        for vsize, va, rawsize, raw in sections:
            if va <= rva < va + max(vsize, rawsize):
                return raw + rva - va
        return rva

    rva, length = struct.unpack_from('<II', data, optional + 120)
    if not rva:
        return set()
    start, dependencies = address(rva), set()
    for index in range(length // 20):
        entry = struct.unpack_from('<IIIII', data, start + index * 20)
        if not any(entry):
            break
        name = address(entry[3])
        dependencies.add(data[name:data.index(b'\0', name)].decode('ascii').lower())
    return dependencies


def check(path):
    with ZipFile(path) as zipped:
        binaries = {Path(n).name.lower(): zipped.read(n) for n in zipped.namelist() if n.endswith(('.dll', '.exe', '.pyd'))}
        for required in ('python.exe', 'python313.dll', 'tesseract.exe', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'):
            if required not in binaries:
                raise ValueError(f'Chybí běhová knihovna: {required}')
        missing = {name: sorted(d for d in imports(data) if d not in binaries and d not in SYSTEM_DLLS
                               and not d.startswith(('api-ms-', 'ext-ms-'))) for name, data in binaries.items()}
        missing = {name: values for name, values in missing.items() if values}
        if missing:
            raise ValueError(f'Chybí DLL v balíčku: {missing}')
        names = zipped.namelist()
        for required in ('Spustit.bat', 'native/tesseract/tessdata/eng.traineddata', 'native/tesseract/tessdata/configs/tsv'):
            if f'Stitkovnik-Windows-x64/{required}' not in names:
                raise ValueError(f'Chybí součást: {required}')
        if any('/vystupy/' in n or '/.venv/' in n or '/.build/' in n or n.endswith(('.so', '.dylib')) for n in names):
            raise ValueError('ZIP obsahuje pracovní data nebo knihovny pro jiný systém.')
    print(f'OK: {len(binaries)} binárních souborů Windows x64; DLL přibalené nebo součástí Windows; model OCR a spouštěč přítomné.')


if __name__ == '__main__':
    check(Path(sys.argv[1]))
