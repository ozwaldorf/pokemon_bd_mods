"""Keep live cliff tuning separate from saved water placements."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import debug_mount


class PlacementScopeTests(unittest.TestCase):
    def test_switch_edit_and_restore_move_scope(self):
        water = {'offset': [0, 0.25, 0], 'rotation': [20, 0, 0], 'scale': [0.7] * 3}
        cliff = {'offset': [0, 1.2, -1.1], 'rotation': [20, 0, 0], 'scale': [0.7] * 3}
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config, placements = directory / 'debug.cfg', directory / 'placements.json'
            placements.write_text(json.dumps({'default': water, 'species': {'9': water},
                'models': {'pm0009_00_00': water}, 'rock_climb': {'9': cliff},
                'rock_climb_models': {'pm0009_00_00': cliff}}))
            config.write_text('enabled=1\nmodel=pm0009_00_00\noffset=0,0.25,0\n'
                              'rotation=20,0,0\nscale=0.7,0.7,0.7\n')

            def run(*args):
                argv = ['debug_mount.py', '--file', str(config), '--placements', str(placements), *args]
                with patch.object(sys, 'argv', argv), patch.object(debug_mount, 'catalog',
                        return_value=['pm0009_00_00']), contextlib.redirect_stdout(io.StringIO()):
                    debug_mount.main()

            run('--move', 'rock-climb', 'set', '--model', '9')
            self.assertIn('offset=0,1.2,-1.1', config.read_text())
            run('set', '--offset', '0', '1.45', '-1.1')
            saved = json.loads(placements.read_text())
            self.assertEqual(saved['species']['9'], water)
            self.assertEqual(saved['models']['pm0009_00_00'], water)
            self.assertEqual(saved['rock_climb']['9']['offset'], [0, 1.45, -1.1])
            run('off')
            self.assertIn('# placement_scope=rock-climb', config.read_text())
            run('--move', 'surf', 'set', '--model', '9')
            self.assertIn('offset=0.0,0.25,0.0', config.read_text())
            self.assertEqual(json.loads(placements.read_text())['rock_climb']['9']['offset'],
                             [0, 1.45, -1.1])
            # Switching scope without a model loads that scope's saved profile.
            run('--move', 'rock-climb', 'set')
            self.assertIn('offset=0.0,1.45,-1.1', config.read_text())
            saved = json.loads(placements.read_text())
            self.assertEqual(saved['rock_climb']['9']['offset'], [0, 1.45, -1.1])
            self.assertEqual(saved['species']['9'], water)


if __name__ == '__main__':
    unittest.main()
