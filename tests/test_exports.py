import csv
import io
import unittest
import zipfile
from xml.etree import ElementTree as ET
from exports import csv_bytes, xlsx_bytes

ROW = {"name": "složka/kamera.png", "fields": {"S/N": "0000123", "MAC": "00:11:22:33:44:55", "IP adresa": "192.168.1.64"}, "text": 'Štítek <kamera> & text\nDruhý řádek', "note": "=1+1", "status": "Ověřeno"}


class ExportTests(unittest.TestCase):
    def test_xlsx_strings_and_xml(self):
        archive = zipfile.ZipFile(io.BytesIO(xlsx_bytes([ROW])))
        for name in archive.namelist():
            ET.fromstring(archive.read(name))
        ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        self.assertEqual(sheet.find('.//x:c[@r="B2"]/x:is/x:t', ns).text, '0000123')
        self.assertEqual(sheet.find('.//x:c[@r="C2"]/x:is/x:t', ns).text, '00:11:22:33:44:55')
        self.assertEqual(sheet.findall('.//x:f', ns), [])
        self.assertEqual(sheet.find('x:autoFilter', ns).attrib['ref'], 'A1:J2')

    def test_csv_unicode_quotes_and_formula_protection(self):
        data = csv_bytes([ROW])
        self.assertTrue(data.startswith(b'\xef\xbb\xbf'))
        rows = list(csv.reader(io.StringIO(data.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(rows[1][1], '0000123')
        self.assertEqual(rows[1][-2], "'=1+1")
        self.assertEqual(rows[1][-1], ROW['text'])

    def test_illegal_xml_characters_are_removed(self):
        archive = zipfile.ZipFile(io.BytesIO(xlsx_bytes([{**ROW, 'text': 'a\x00b\x0bc'}])))
        ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))


if __name__ == '__main__':
    unittest.main()
