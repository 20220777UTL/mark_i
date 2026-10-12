import tempfile
import unittest
from pathlib import Path

from PythonScripts.ClientPractice import stage_next_team


class ClientPracticeTests(unittest.TestCase):
    def test_blue_then_yellow_restores_ini_byte_for_byte(self):
        original = (b'[Alert]\r\nIsSimulation=true\r\n'
                    b'[ZAlert]\r\nIsRight=false\r\nIsYellow=false\r\nCustom=keep\r\n'
                    b'[Other]\r\nValue=untouched\r\n')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'zss.ini'
            path.write_bytes(original)
            stage_next_team(path, current_yellow=False)
            self.assertEqual(path.read_bytes(), original.replace(
                b'IsRight=false\r\nIsYellow=false',
                b'IsRight=true\r\nIsYellow=true'))
            stage_next_team(path, current_yellow=True)
            self.assertEqual(path.read_bytes(), original)

    def test_missing_team_setting_leaves_ini_intact(self):
        original = b'[ZAlert]\nIsRight=false\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'zss.ini'
            path.write_bytes(original)
            with self.assertRaises(ValueError):
                stage_next_team(path, current_yellow=False)
            self.assertEqual(path.read_bytes(), original)

    def test_qt_spaced_settings_keep_original_format(self):
        original = (b'[ZAlert]\r\nIsRight = false\r\nIsYellow = false\r\n'
                    b'[Other]\r\nValue = untouched\r\n')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'zss.ini'
            path.write_bytes(original)
            stage_next_team(path, current_yellow=False)
            self.assertEqual(path.read_bytes(), original.replace(
                b'IsRight = false\r\nIsYellow = false',
                b'IsRight = true\r\nIsYellow = true'))
            stage_next_team(path, current_yellow=True)
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
