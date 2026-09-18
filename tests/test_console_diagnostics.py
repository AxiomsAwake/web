import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from console_diagnostics import ConsoleDiagnostics


WARNING = 'WARNING: instance_reset_physics_interpolation() is deprecated.'
LOCATION = '   at: _instance_reset_physics_interpolation_bind_compat_104269 (servers/rendering/rendering_server.compat.inc:62)'


class ConsoleDiagnosticsTests(unittest.TestCase):
    def test_split_native_warning_is_retained_not_promoted_to_error(self):
        log = ConsoleDiagnostics()
        self.assertFalse(log.is_error('error', WARNING))
        self.assertFalse(log.is_error('error', LOCATION))
        self.assertEqual(log.warnings, [WARNING + '\n' + LOCATION])

    def test_warning_does_not_mask_real_errors_or_unpaired_locations(self):
        for message in ['SCRIPT ERROR: failed', 'ERROR: failed', 'Unhandled application error',
                        LOCATION + '\nERROR: failed', '   at: arbitrary application error']:
            with self.subTest(message=message):
                log = ConsoleDiagnostics()
                log.is_error('error', WARNING)
                self.assertTrue(log.is_error('error', message))
        self.assertTrue(ConsoleDiagnostics().is_error('error', LOCATION))

    def test_only_one_immediately_adjacent_native_location_is_exempt(self):
        log = ConsoleDiagnostics()
        log.is_error('error', WARNING)
        self.assertFalse(log.is_error('error', LOCATION))
        self.assertTrue(log.is_error('error', LOCATION))
        log.is_error('error', WARNING)
        log.is_error('log', 'another message')
        self.assertTrue(log.is_error('error', LOCATION))

    def test_warning_state_is_page_local_and_evidence_is_bounded(self):
        log = ConsoleDiagnostics()
        for _ in range(30):
            log.is_error('error', 'WARNING: ' + 'x' * 3000)
            log.is_error('error', LOCATION)
        self.assertEqual(len(log.warnings), 20)
        self.assertTrue(all(len(item) <= 2000 for item in log.warnings))
        self.assertTrue(ConsoleDiagnostics().is_error('error', LOCATION))
        self.assertFalse(log.is_error('warning', 'browser warning'))
