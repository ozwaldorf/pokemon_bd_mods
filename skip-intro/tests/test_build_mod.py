import hashlib
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lz4.block

spec = importlib.util.spec_from_file_location(
    "skip_intro_build", Path(__file__).resolve().parents[1] / "scripts/build_mod.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def nso(text=b"example text", compressed=False):
    header = bytearray(0x100)
    header[:4] = b"NSO0"
    header[0x40:0x50] = bytes.fromhex(mod.BUILD_ID)
    struct.pack_into("<I", header, 0xC, int(compressed))
    struct.pack_into("<III", header, 0x10, 0x100, 0, len(text))
    payload = lz4.block.compress(text, store_size=False) if compressed else text
    struct.pack_into("<I", header, 0x60, len(payload))
    return header + payload


class StartupPatchTests(unittest.TestCase):
    def test_branch_encoding(self):
        self.assertEqual(mod.branch(mod.PATCH_RVA, mod.ORIGINAL_TARGET).hex(), "47000014")
        self.assertEqual(mod.branch(mod.PATCH_RVA, mod.LOAD_TARGET).hex(), "63010014")
        self.assertEqual(mod.branch(4, 0).hex(), "ffffff17")
        for target in (1, 1 << 27, -(1 << 27) - 4):
            with self.subTest(target=target), self.assertRaises(ValueError):
                mod.branch(0, target)

    def test_reads_compressed_and_uncompressed_nso(self):
        with tempfile.TemporaryDirectory() as temporary:
            main = Path(temporary) / "main"
            for compressed in (False, True):
                with self.subTest(compressed=compressed):
                    main.write_bytes(nso(compressed=compressed))
                    self.assertEqual(mod.executable_text(main), b"example text")

    def test_rejects_wrong_build_and_truncated_executable(self):
        wrong_build = nso()
        wrong_build[0x40] ^= 1
        wrong_layout = nso()
        struct.pack_into("<I", wrong_layout, 0x14, 4)
        with tempfile.TemporaryDirectory() as temporary:
            main = Path(temporary) / "main"
            for invalid in (b"NSO0", wrong_build, wrong_layout, nso()[:-1]):
                with self.subTest(invalid=bytes(invalid[:16])):
                    main.write_bytes(invalid)
                    with self.assertRaises(ValueError):
                        mod.executable_text(main)

    def test_packages_only_patch_and_replaces_stale_output(self):
        text = bytearray(mod.LOAD_TARGET + 4)
        text[mod.PATCH_RVA:mod.PATCH_RVA + 4] = bytes.fromhex("47000014")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "mod"
            output.mkdir()
            (output / "stale").write_text("old artifact")
            with patch.object(mod, "executable_text", return_value=text):
                mod.build(Path(temporary), output)
            self.assertFalse((output / "stale").exists())
            exefs = output / "exefs"
            self.assertEqual([p.name for p in exefs.iterdir()], ["skip-intro-v1.3.0.pchtxt"])
            patch_data = (exefs / "skip-intro-v1.3.0.pchtxt").read_bytes()
            self.assertIn(b"@flag offset_shift 0x100", patch_data)
            self.assertIn(b"02CB5BB4 63010014", patch_data)
            manifest = json.loads((output / "build_manifest.json").read_text())
            self.assertEqual(manifest["patch_sha256"], hashlib.sha256(patch_data).hexdigest())
            # A changed executable must fail before replacing a successful build.
            text[mod.PATCH_RVA] ^= 1
            with patch.object(mod, "executable_text", return_value=text):
                with self.assertRaisesRegex(ValueError, "expected opening branch"):
                    mod.build(Path(temporary), output)
            self.assertEqual((exefs / "skip-intro-v1.3.0.pchtxt").read_bytes(), patch_data)


if __name__ == "__main__":
    unittest.main()
