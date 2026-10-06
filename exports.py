"""Dependency-free XLSX and Czech Excel-friendly CSV exports."""
import csv
import io
import re
import zipfile
from xml.sax.saxutils import escape


def table(rows):
    keys = list(dict.fromkeys(["S/N", "MAC", "Model", "Výrobce", "Napájení"] + [k for r in rows for k in r.get("fields", {})]))
    headers = ["Soubor", *keys, "Kontrola", "Poznámka", "Rozpoznaný text"]
    data = [[r.get("name", ""), *[r.get("fields", {}).get(k, "") for k in keys],
             r.get("status", ""), r.get("note", ""), r.get("text", "") + ('\n\nPůvodní čtení celého obrázku:\n' + r['originalText'] if r.get('originalText') and r['originalText'] != r.get('text', '') else '')] for r in rows]
    return [headers, *data]


def csv_bytes(rows):
    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=";", quoting=csv.QUOTE_ALL)
    for row in table(rows):
        # Spreadsheet applications can execute formulas even in quoted CSV cells.
        writer.writerow(["'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else str(v) for v in row])
    return out.getvalue().encode("utf-8-sig")


def column(index):
    out = ""
    while index:
        index, digit = divmod(index - 1, 26)
        out = chr(65 + digit) + out
    return out


def xlsx_bytes(rows):
    values = table(rows)
    sheet_rows = []
    for i, row in enumerate(values, 1):
        cells = []
        for j, value in enumerate(row, 1):
            value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))[:32767]
            style = ' s="1"' if i == 1 else ' s="2"'
            cells.append(f'<c r="{column(j)}{i}" t="inlineStr"{style}><is><t xml:space="preserve">{escape(value)}</t></is></c>')
        sheet_rows.append(f'<row r="{i}">' + "".join(cells) + '</row>')
    last = f"{column(len(values[0]))}{len(values)}"
    files = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Štítky kamer" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF285A45"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="3"><xf/><xf fontId="1" fillId="2" applyFont="1" applyFill="1"/><xf numFmtId="49" applyNumberFormat="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="38" customWidth="1"/><col min="2" max="' + str(len(values[0]) - 1) + '" width="25" customWidth="1"/><col min="' + str(len(values[0])) + '" max="' + str(len(values[0])) + '" width="65" customWidth="1"/></cols><sheetData>' + "".join(sheet_rows) + f'</sheetData><autoFilter ref="A1:{last}"/></worksheet>',
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + content)
    return out.getvalue()
