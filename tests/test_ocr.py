import unittest
import io
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import ocr
import app
from app import barcode_serial, label_crop
from extractor import DEFAULT_RULES, extract
from ocr import reconstruct, text_skew
from PIL import Image


class OCRTests(unittest.TestCase):
    def test_windows_ocr_uses_bundled_executable_and_model_without_path(self):
        tsv = 'level\tleft\ttop\twidth\theight\tconf\ttext\n5\t10\t20\t30\t10\t95\tštítek\n'
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / 'český štítek.png'
            image.write_bytes(b'example image bytes')
            with patch.object(ocr.sys, 'platform', 'win32'), patch.object(ocr.Path, 'is_file', return_value=True), patch.object(ocr.shutil, 'which', return_value=None), patch.object(ocr.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=tsv.encode('utf-8'))) as run:
                text, confidence = ocr.tesseract_read(image, 6)
                self.assertEqual((text, confidence), ('štítek', 95))
                self.assertEqual(run.call_args.args[0][:2], [str(ocr.ROOT / 'native' / 'tesseract' / 'tesseract.exe'), 'stdin'])
                self.assertEqual(run.call_args.kwargs['input'], image.read_bytes())
                self.assertEqual(run.call_args.kwargs['env']['TESSDATA_PREFIX'], 'tessdata')
                self.assertEqual(run.call_args.kwargs['cwd'], ocr.ROOT / 'native' / 'tesseract')
                self.assertIn('load_system_dawg=0', run.call_args.args[0])
                self.assertIn('load_freq_dawg=0', run.call_args.args[0])

    def test_tesseract_spans_use_image_dimensions_for_crop_coordinates(self):
        tsv = 'level\tleft\ttop\twidth\theight\tconf\ttext\n5\t100\t50\t200\t20\t95\tS/N:\n'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'label.png'
            Image.new('RGB', (1000, 500)).save(path)
            with patch.object(ocr, 'tesseract_binary', return_value='tesseract'), patch.object(ocr.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=tsv.encode())):
                text, confidence, spans = ocr.tesseract_read(path, 11, include_spans=True)
            self.assertEqual((text, confidence), ('S/N:', 95))
            self.assertEqual([spans[0][key] for key in ('left', 'top', 'width', 'height')], [.1, .1, .2, .04])

    def test_skew_uses_multiple_lines_and_preserves_rotation_direction(self):
        spans = [{'text': 'word', 'confidence': 90, 'line': (1, 1, line),
                  'left': x, 'top': line * 60 - x * .07, 'width': 40, 'height': 20}
                 for line in (1, 2) for x in (0, 100, 200)]
        self.assertAlmostEqual(text_skew(spans), -4, delta=.1)
        self.assertEqual(text_skew(spans[:3]), 0)
        for span in spans:
            span['top'] = span['line'][2] * 60
        self.assertEqual(text_skew(spans), 0)

    def test_windows_pipeline_recovers_small_label_with_a_crop(self):
        data = io.BytesIO()
        Image.new('RGB', (3000, 2000), 'white').save(data, format='PNG')
        spans = [{'text': 'S/N:', 'left': .4, 'top': .45, 'width': .1, 'height': .01},
                 {'text': 'MAC:', 'left': .4, 'top': .48, 'width': .1, 'height': .01}]
        sizes = []

        def read(path, psm, include_spans=False):
            with Image.open(path) as image:
                sizes.append(image.size)
            if include_spans:
                return 'S/N:\nMAC:', 50, spans
            return 'S/N: 000123456789\nMAC: A4:14:37:00:12:AB', 95

        with patch.object(app, 'vision_supported', return_value=False), patch.object(app, 'tesseract_binary', return_value='tesseract'), patch.object(app, 'tesseract_read', side_effect=read), patch.object(app.zxingcpp, 'read_barcodes', return_value=[]):
            result = app.ocr_image(data.getvalue(), DEFAULT_RULES, rotate=False)
        self.assertEqual(result['fields']['S/N'], '000123456789')
        self.assertEqual(result['fields']['MAC'], 'A4:14:37:00:12:AB')
        self.assertIn('výřez štítku', result['engine'])
        self.assertEqual(len(sizes), 2)
        self.assertLess(sizes[1][0], sizes[0][0])
        self.assertGreater(sizes[1][0], 1000)
        self.assertEqual(result['originalText'], 'S/N:\nMAC:')

    def test_mac_ignores_windows_executable_and_uses_installed_tesseract(self):
        with patch.object(ocr.sys, 'platform', 'darwin'), patch.object(ocr.Path, 'is_file', return_value=True), patch.object(ocr.shutil, 'which', return_value='/opt/homebrew/bin/tesseract'):
            self.assertEqual(ocr.tesseract_binary(), '/opt/homebrew/bin/tesseract')

    def test_portable_vision_runs_without_a_compiler(self):
        with patch.object(ocr.sys, 'platform', 'darwin'), patch.object(ocr.Path, 'is_file', return_value=True), patch.object(ocr.shutil, 'which', return_value=None), patch.object(ocr.subprocess, 'run') as run:
            self.assertTrue(ocr.vision_supported())
            self.assertEqual(ocr.vision_binary(), ocr.ROOT / 'native' / 'label-vision')
            run.assert_not_called()

    def test_incomplete_portable_package_does_not_compile_in_temp_directory(self):
        with patch.object(ocr.sys, 'frozen', True, create=True), patch.object(ocr.Path, 'is_file', return_value=False), patch.object(ocr.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'chybí pomocný program'):
                ocr.vision_binary()
            run.assert_not_called()

    def test_fragments_are_ordered_by_position_not_ocr_block(self):
        spans = [
            {'text': 'MAC:', 'left': 10, 'top': 60, 'width': 30, 'height': 10, 'confidence': 90},
            {'text': 'ABC123', 'left': 80, 'top': 21, 'width': 70, 'height': 10, 'confidence': 90},
            {'text': 'S/N:', 'left': 10, 'top': 20, 'width': 30, 'height': 10, 'confidence': 90},
            {'text': '00:11:22:33:44:55', 'left': 80, 'top': 60, 'width': 120, 'height': 10, 'confidence': 90},
        ]
        text, confidence = reconstruct(spans)
        self.assertEqual(text, 'S/N: ABC123\nMAC: 00:11:22:33:44:55')
        self.assertEqual(confidence, 90)

    def test_barcode_corrects_only_a_corroborated_printed_identifier(self):
        candidates = [extract('S/N: 6KOC3C2PAG58004\nMAC: 24:52:6A:2A:82:8E')]
        codes = [{'payload': '6K0C3C2PAG5B004', 'symbology': 'QR'}]
        self.assertEqual(barcode_serial(codes, candidates), '6K0C3C2PAG5B004')
        self.assertIsNone(barcode_serial([{'payload': '123456789012', 'symbology': 'QR'}], candidates))
        self.assertIsNone(barcode_serial([{'payload': 'https://example.com', 'symbology': 'QR'}], candidates))

    def test_a_mac_barcode_cannot_become_a_serial(self):
        candidates = [extract('S/N: 001122334455\nMAC: 00:11:22:33:44:55')]
        self.assertIsNone(barcode_serial([{'payload': '001122334455', 'symbology': 'QR'}], candidates))

    def test_conflicting_barcodes_do_not_choose_an_arbitrary_serial(self):
        candidates = [extract('S/N: ABCD12345678')]
        codes = [{'payload': 'ABCD12345678', 'symbology': 'QR'}, {'payload': 'ABCD12345679', 'symbology': 'Code128'}]
        self.assertIsNone(barcode_serial(codes, candidates))

    def test_crop_keeps_unrecognized_nearby_heading_and_mac_suffix(self):
        spans = [
            {'text': 'bad heading', 'left': .2, 'top': .22, 'width': .55, 'height': .05},
            {'text': 'SN:12345678', 'left': .2, 'top': .4, 'width': .3, 'height': .04},
            {'text': 'MAC:00:11:22:33', 'left': .2, 'top': .45, 'width': .3, 'height': .04},
            {'text': '44:55', 'left': .53, 'top': .43, 'width': .08, 'height': .04},
        ]
        crop = label_crop(Image.new('RGB', (1000, 1000)), spans)
        self.assertGreaterEqual(crop.width, 600)


if __name__ == '__main__':
    unittest.main()
