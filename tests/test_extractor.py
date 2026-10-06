import copy
import unittest
from extractor import DEFAULT_RULES, extract, validate_rules


class ExtractionTests(unittest.TestCase):
    def test_standard_camera_label(self):
        result = extract("HIKVISION\nModel: DS-2CD2043G2-I\nS/N: 00123456789\nMAC: A4:14:37:00:12:AB\n12 V DC\nIP Address: 192.168.1.64")
        self.assertEqual(result["fields"]["S/N"], "00123456789")
        self.assertEqual(result["fields"]["MAC"], "A4:14:37:00:12:AB")
        self.assertEqual(result["fields"]["Výrobce"], "HIKVISION")
        self.assertEqual(result["fields"]["Napájení"], "12 V DC")
        self.assertEqual(result["fields"]["IP Address"], "192.168.1.64")
        self.assertEqual(result["warnings"], [])

    def test_same_line_fields(self):
        fields = extract("S/N: ABC123 MAC: aabbccddeeff Model: IPC-HFW1234")['fields']
        self.assertEqual(fields['S/N'], 'ABC123')
        self.assertEqual(fields['MAC'], 'AA:BB:CC:DD:EE:FF')
        self.assertEqual(fields['Model'], 'IPC-HFW1234')

    def test_value_on_next_line(self):
        fields = extract("Serial No.\n00777XYZ\nMAC Address\n00-11-22-33-44-55")['fields']
        self.assertEqual(fields['S/N'], '00777XYZ')
        self.assertEqual(fields['MAC'], '00:11:22:33:44:55')

    def test_spaced_slash_and_dotted_mac(self):
        fields = extract("S / N : 00001234\nMAC: aabb.ccdd.eeff")['fields']
        self.assertEqual(fields['S/N'], '00001234')
        self.assertEqual(fields['MAC'], 'AA:BB:CC:DD:EE:FF')

    def test_serial_is_not_unlabelled_mac(self):
        result = extract("SN: 001122334455")
        self.assertEqual(result['fields']['MAC'], '')
        self.assertIn('Chybí MAC', result['warnings'])

    def test_suspicious_trailing_ocr_character_is_preserved(self):
        result = extract('SN: ABC123|\nMAC: 001122334455')
        self.assertEqual(result['fields']['S/N'], 'ABC123|')

    def test_invalid_mac_is_preserved_for_review(self):
        result = extract("SN: 123\nMAC: A4:14:37:OO:12:AB")
        self.assertEqual(result['fields']['MAC'], 'A4:14:37:OO:12:AB')
        self.assertIn('MAC nemá platný formát', result['warnings'])

    def test_unlabelled_separated_mac(self):
        self.assertEqual(extract("SN 123\n00 11 22 33 44 55")['fields']['MAC'], '00:11:22:33:44:55')

    def test_multiple_mac_addresses(self):
        result = extract("SN: 123\nMAC: 001122334455\nMAC: AABBCCDDEEFF")
        self.assertEqual(result['fields']['MAC'], '00:11:22:33:44:55; AA:BB:CC:DD:EE:FF')
        self.assertTrue(any('Více MAC' in w for w in result['warnings']))

    def test_empty_label_does_not_steal_next_field(self):
        result = extract("SN:\nMAC: 001122334455")
        self.assertEqual(result['fields']['S/N'], '')
        self.assertEqual(result['fields']['MAC'], '00:11:22:33:44:55')

    def test_custom_rules_and_czech_names(self):
        rules = copy.deepcopy(DEFAULT_RULES)
        rules['Umístění'] = ['Location', 'Umístění']
        result = extract("Sériové číslo: 000XYZ\nMAC adresa: 00:11:22:33:44:55\nUmístění: Brána A", rules)
        self.assertEqual(result['fields']['S/N'], '000XYZ')
        self.assertEqual(result['fields']['Umístění'], 'Brána A')

    def test_literal_rule_not_regex(self):
        rules = copy.deepcopy(DEFAULT_RULES)
        rules['Test'] = ['(a+b)']
        self.assertEqual(extract('(a+b): hodnota', rules)['fields']['Test'], 'hodnota')

    def test_invalid_rules(self):
        for value in [None, [], {}, {'S/N': ['SN'], 'MAC': []}]:
            with self.assertRaises(ValueError):
                validate_rules(value)

    def test_dahua_sin_ocr_alias(self):
        self.assertEqual(extract('SIN: 7F031A6PAG7FE41')['fields']['S/N'], '7F031A6PAG7FE41')

    def test_mac_with_spaces_around_colons_and_cyrillic_lookalikes(self):
        result = extract('SN: 102104069562\nМАС: 00: 18:85:35:B4:4А')
        self.assertEqual(result['fields']['MAC'], '00:18:85:35:B4:4A')

    def test_dahua_model_without_field_name(self):
        fields = extract('DH — IPC — HDBW5831RP — ZE\n12V = ,1A,POE')['fields']
        self.assertEqual(fields['Model'], 'DH-IPC-HDBW5831RP-ZE')
        self.assertEqual(fields['Napájení'], '12V = ,1A,POE')


if __name__ == '__main__':
    unittest.main()
