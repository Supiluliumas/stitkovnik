# Štítkovník

Jednoduchá lokální aplikace pro převod fotografií výrobních štítků kamer do tabulky a Excelu. Na Macu používá Apple Vision, automatický výřez štítku a čtení čárových / QR kódů. Tesseract slouží jako další pokus při neúplném čtení a jako OCR na ostatních systémech. Obrázky se nikam neodesílají. Rozhraní je česky a otevírá se v běžném prohlížeči.

## Stáhnout a spustit bez instalace

Hotové balíčky najdete v [nejnovějším vydání na GitHubu](https://github.com/Supiluliumas/stitkovnik/releases/latest).

| Systém | Stáhnout ZIP | Spustit po rozbalení |
| --- | --- | --- |
| Windows 10/11, 64bit Intel/AMD | [Stitkovnik-Windows-x64.zip](https://github.com/Supiluliumas/stitkovnik/releases/latest/download/Stitkovnik-Windows-x64.zip) | `Spustit.bat` |
| Mac s Apple Silicon (M1 a novější), macOS 13+ | [Stitkovnik-macOS-arm64.zip](https://github.com/Supiluliumas/stitkovnik/releases/latest/download/Stitkovnik-macOS-arm64.zip) | `Spustit.command` |

Rozbalte **celý ZIP**, pak dvakrát klikněte na spouštěč. Rozhraní se otevře v prohlížeči. Python, OCR ani další knihovny nemusíte instalovat; při práci není potřeba internet. Příkazové okno nechte otevřené. Před ukončením exportujte výsledky do Excelu; nástroj ukončíte Ctrl+C v příkazovém okně.

Na GitHubu stahujte uvedené balíčky v části **Assets**. Automatický archiv **Source code** obsahuje zdrojový kód a není přenosnou aplikací. Varianta pro Mac je určena pro Apple Silicon; pro Intel Mac zatím není hotové vydání.

Balíček pro Mac nemá notarizaci Apple. Pokud macOS otevření zablokuje, můžete je povolit v Nastavení systému → Soukromí a zabezpečení. Stav ověření konkrétního vydání je uvedený v jeho poznámkách.

## Přenosný balíček pro sdílení

Ve složce `dist` vzniká ZIP `Stitkovnik-macOS-arm64.zip` pro Macy s Apple Silicon (M1 a novější). Příjemce rozbalí celý ZIP a dvakrát klikne na `Spustit.command`. Python, Homebrew, Xcode ani Tesseract nemusí instalovat; balíček obsahuje běhové prostředí, knihovny, rozhraní a předem sestavený Apple Vision pomocný program. Spuštění i OCR fungují bez internetu. Terminál zůstává otevřený; ukončení je Ctrl+C.

Sdílejte celý ZIP. Obsahuje pouze aplikaci, návod, licence a umělé ukázkové štítky. Tabulka a pravidla zůstávají v úložišti konkrétního prohlížeče; s nástrojem se nepřenášejí. Pro přenos výsledků použijte Excel nebo CSV.

Balíček nemá podpis Developer ID ani notarizaci Apple. macOS může vyžadovat povolení otevření v Nastavení systému → Soukromí a zabezpečení. Kompatibilita je ověřená na systému použitém při sestavení; starší verze macOS vyžadují samostatné ověření. Tento ZIP není určený pro Windows ani Intel Mac.

Nový build na cílovém Macu:

```sh
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python tools/build_portable.py
```

Sestavení potřebuje Python 3.11+ (kvůli kontrolnímu součtu), Swift Command Line Tools a při instalaci závislostí internet. Skript používá [PyInstaller](https://www.pyinstaller.org/en/stable/usage.html), přidává statické soubory a hotový OCR program a vytvoří ZIP se SHA-256. Na Intel Macu vytvoří variantu `x86_64`; build pro jiný operační systém vyžaduje samostatný postup s odpovídajícím OCR.

Pro podporu starších Maců použijte Python s odpovídající minimální verzí macOS. Build odmítne Python vyžadující novější macOS než 13. Pro zdejší balíček byl použit Python 3.13 z [uv](https://docs.astral.sh/uv/guides/install-python/) v samostatném prostředí:

```sh
UV_PYTHON_INSTALL_DIR="$PWD/.build/python" .venv/bin/uv python install 3.13
.venv/bin/uv venv --python .build/python/cpython-3.13-macos-aarch64-none/bin/python3.13 .build/portable-venv
.venv/bin/uv pip install --python .build/portable-venv/bin/python -r requirements-build.txt
.build/portable-venv/bin/python tools/build_portable.py
```

Tyto příkazy vyžadují dostupné `uv` (například `.venv/bin/python -m pip install uv`).

Ověření hotového ZIPu (rozbalí jej do dočasné cesty s mezerami a diakritikou, spustí bez externího Pythonu a OCR v PATH, přečte oba ukázkové štítky a ověří XLSX/CSV):

```sh
.venv/bin/python tools/check_portable.py dist/Stitkovnik-macOS-arm64.zip
```

## Přenosný balíček pro Windows

`dist/Stitkovnik-Windows-x64.zip` je varianta pro Windows 10/11 na 64bitových procesorech Intel a AMD. Rozbalte celý ZIP a dvakrát klikněte na `Spustit.bat`. Otevře se příkazové okno a rozhraní v prohlížeči. Okno nechte otevřené; ukončení je Ctrl+C. Python ani Tesseract se neinstalují a při spuštění se nic nestahuje.

Balíček obsahuje [oficiální vestavěný Python](https://docs.python.org/3.13/using/windows.html#the-embeddable-package), Windows knihovny Pillow, HEIF a ZXing, [Tesseract pro Windows](https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.0) a anglický model [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast). Model čte identifikátory a anglické názvy polí ze štítků; rozhraní zůstává české. Výsledky OCR se mohou lišit od Apple Vision na Macu.

Microsoft Visual C++ runtime potřebný pro ZXing je přibalený přímo ve složce `runtime`; samostatná instalace redistributable není potřeba. DLL pocházejí z [oficiální distribuce Microsoftu](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) a používají [lokální nasazení](https://learn.microsoft.com/en-us/cpp/windows/deployment-in-visual-cpp).

ZIP obsahuje aplikaci, licence, zdroje závislostí a umělé štítky. Sdílejte jej celý. Vlastní fotografie a pracovní exporty v něm nejsou; tabulka a pravidla zůstávají v prohlížeči konkrétního počítače. Výsledky ověření konkrétního vydání najdete na stránce Releases.

Sestavení je možné i na Macu nebo Linuxu. Vyžaduje Python 3.11+ s pip, internet a [7-Zip](https://www.7-zip.org/download.html) dostupný jako `7zz`/`7z` (nebo předaný přes `--sevenzip`). Příjemce ZIPu tyto nástroje nepotřebuje:

```sh
.venv/bin/python tools/build_windows_portable.py --sevenzip .build/windows/7zip/7zz
```

Skript stáhne distribuce pro Windows x64, ověří SHA-256 Pythonu, OCR a modelu, rozbalí OCR instalátor bez jeho spuštění a připraví čistý ZIP. Windows wheels instaluje do soukromé složky `runtime/Lib/site-packages`. Verze knihoven jsou uvedené v `requirements-windows-portable.txt`, jejich kontrolní součty a zdroje v `licence/ZDROJE.json`. Vedle ZIPu vznikne soubor `.zip.sha256`.

Ověření ve Windows (ve zdrojovém projektu; lze použít Python z rozbaleného balíčku):

```bat
rozbaleny-balicek\runtime\python.exe -X utf8 tools\check_portable.py dist\Stitkovnik-Windows-x64.zip
```

Test rozbalí ZIP do dočasné cesty s mezerami a diakritikou, použije jen přibalený Python a OCR, přečte oba ukázkové štítky a ověří XLSX/CSV. Workflow [Verify portable packages](https://github.com/Supiluliumas/stitkovnik/actions/workflows/portable.yml) sestavuje a ověřuje balíčky na Windows a macOS Apple Silicon; každý běh zahrnuje také jednotkové testy. Konzole při sestavení ve Windows má používat UTF-8 (`python -X utf8` nebo `PYTHONUTF8=1`).

## Spuštění ze zdrojového kódu na macOS

Dvakrát klikněte na **Spustit.command**. Otevře se Terminál a aplikace v prohlížeči. Terminál nechte při práci otevřený; aplikaci ukončíte pomocí Ctrl+C.

Vyžaduje Python 3.10+ a na Macu nástroje Swift z Command Line Tools (`xcode-select --install`) nebo Tesseract. V tomto prostředí jsou již dostupné. Při prvním spuštění se automaticky vytvoří virtuální prostředí, nainstalují knihovny z requirements.txt a připraví lokální pomocný program pro Apple Vision. Další zpracování funguje bez internetu.

Pokud Tesseract na jiném Macu chybí, nainstalujte jej pomocí Homebrew:

```sh
brew install tesseract
```

Ruční spuštění, použitelné i na Linuxu a Windows s nainstalovaným Tesseractem v PATH:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Na Windows použijte `.venv\Scripts\python.exe` místo `.venv/bin/python`. Výchozí adresa je `http://127.0.0.1:8765`; je-li port obsazený, aplikace vybere volný a vypíše adresu. Parametr `--no-browser` vypne automatické otevření prohlížeče.

## Postup

1. Zvolte **Vybrat složku**, potvrďte výběr souborů v prohlížeči, nebo načtěte jednotlivé obrázky. Výběr složky zahrne také podsložky. Podporované jsou JPG, PNG, TIFF, BMP, WebP a HEIC/HEIF do 30 MB a 40 megapixelů; z vícestránkového TIFF se čte první snímek. Přetažení podporuje jednotlivé soubory; složku načtěte tlačítkem. Při zaškrtnuté volbě „Při opětovném načtení aktualizovat neověřené řádky“ nové čtení nahradí neověřené hodnoty souborů se stejným názvem a cestou. Ověřené řádky a poznámky se zachovají. Pokud nový pokus selže, starší výsledek zůstane v tabulce.
2. Každý obrázek vytvoří jeden řádek. Čtou se **S/N, MAC, model, výrobce, napájení, P/N a verze**. Další dvojice „název: hodnota“ se přidají jako samostatná pole. Celý rozpoznaný text je vždy dostupný v detailu a exportu.
3. Upravte S/N, MAC nebo model přímo v tabulce. Kliknutím na název souboru otevřete fotografii, všechny údaje, poznámku a OCR text. Po kontrole označte **Údaje jsem ověřil/a podle štítku**. Úprava údajů zruší předchozí ověření.
4. V **Pravidlech rozpoznávání** lze upravit názvy polí ze štítků a přidat vlastní sloupce. Názvy se porovnávají bez ohledu na velikost písmen a českou diakritiku. Hodnota se očekává za názvem na stejném nebo následujícím řádku. V detailu lze upravit OCR text a znovu přiřadit pole podle nových pravidel; to nahradí dosavadní hodnoty v otevřeném detailu.
5. **Exportovat Excel** vytvoří skutečný `.xlsx` se všemi řádky, všemi poli, stavem kontroly, poznámkou a rozpoznaným textem. CSV je odděleno středníkem a obsahuje UTF-8 BOM pro český Excel. Filtry a hledání mění zobrazení; export vždy obsahuje celou tabulku.

MAC se sjednocují na formát `AA:BB:CC:DD:EE:FF`. S/N a všechny další hodnoty jsou v XLSX uloženy jako text, včetně úvodních nul. CSV může Excel při přímém otevření automaticky převést; pro zachování identifikátorů použijte XLSX nebo importujte CSV sloupce jako text.

Chybějící údaje, neplatný MAC, více identifikátorů na jednom obrázku, rozdílné výsledky čtení, duplicity a nízká jistota OCR jsou označeny ke kontrole. Stav „Rozpoznáno“ znamená výsledek OCR; „Ověřeno“ vyžaduje vaše potvrzení a splnění kontroly polí. Jistota OCR je průměr jistoty textových pozorování vážený počtem znaků, nikoli záruka správnosti S/N nebo MAC. Hodnoty různých OCR systémů nejsou přímo srovnatelné.

Tabulka a pravidla se automaticky ukládají do úložiště prohlížeče pro danou adresu aplikace. Fotografie se do něj neukládají, takže po obnovení stránky není náhled původního souboru dostupný. Jiný prohlížeč nebo port má samostatné úložiště. Před ukončením práce doporučujeme export; anonymní režim nemusí uchovat výsledky.

## Kvalita fotografií

Nejlépe funguje jeden štítek na obrázek, fotografovaný zblízka, ostře, bez odlesků. Aplikace respektuje EXIF orientaci a při neúspěšném čtení zkouší další otočení. Apple Vision dostává původní obraz v plném rozlišení, poté se z polohy textu vytvoří výřez štítku a přečte se znovu. Tesseract dostává samostatně připravený obraz; různé bloky textu se spojují podle polohy. Na Windows a ostatních systémech s Tesseractem se při neúplném nebo nejistém čtení také vytvoří výřez podle rozpoznaných názvů polí, zvětší se a přečte v režimech pro blok i rozptýlený text. Pokud poloha slov na alespoň dvou řádcích umožní odhadnout mírný náklon, zkusí se i narovnaný výřez. Slovníkové opravy Tesseractu jsou vypnuté, aby nepreferoval běžná slova před identifikátory. Tyto další pokusy mohou prodloužit zpracování obtížných fotek; přesnost Windows je potřeba ověřit na skutečných fotografiích, nelze ji odvodit z výsledků Apple Vision. Silně šikmé, rozmazané nebo zakřivené štítky mohou vyžadovat ruční opravu.

S/N z čárového nebo QR kódu se použije jen tehdy, když odpovídá textu přečtenému ze štítku (včetně malých OCR chyb) a nejde o přečtenou MAC adresu. Celý odkaz z QR se do S/N nepřevádí. Původní text ani sériová čísla se neopravují slepou záměnou O/0 nebo B/8. V detailu je uvedeno, zda S/N pochází z kódu. Pokud výřez přinesl jiné čtení, export zahrnuje i původní OCR celého obrázku. PDF zatím není podporované; prohlížeč nemusí zobrazit náhled HEIC či TIFF, i když je jejich OCR dostupné.

## Ukázkové štítky a ověření

Složka `ukazkove-stitky` obsahuje dva umělé štítky pro vyzkoušení, jeden otočený o 90°. Nejde o údaje skutečných zařízení. Znovu je lze vytvořit:

```sh
.venv/bin/python tools/make_demo.py
.venv/bin/python -m unittest discover -v
```

Testy pokrývají extrakci identifikátorů a vlastních polí, neplatné a vícenásobné MAC, zachování úvodních nul a strukturu XLSX/CSV.

Volitelný test celého postupu v prohlížeči (aplikace musí běžet):

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_smoke.py
```

OCR používá Apple Vision bez jazykových oprav identifikátorů, [rozhraní Tesseract s TSV výstupem](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html), [ZXing-C++](https://github.com/zxing-cpp/zxing-cpp) a přípravu obrázků pomocí [Pillow ImageOps](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html).
