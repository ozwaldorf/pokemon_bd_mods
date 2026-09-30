"""Regression tests for the descriptor that prevented Eden from booting."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from npdm import validate_process_descriptor


def descriptor(debug=0x2ffff):
    caps = [0x20073b7, 0x1fffffef, 0x3fffffef, 0x47e60fef,
            0x7fffffef, 0x9ff7ffef, 0xa0001fef,
            0x5fff, 0x48bfff, 0x2007fff, debug]
    data = bytearray(0xc0 + 4 * len(caps))
    data[:4] = b"META"
    struct.pack_into("<II", data, 0x70, 0x80, len(data) - 0x80)
    data[0x80:0x84] = b"ACI0"
    struct.pack_into("<Q", data, 0x90, 0x0100000011D90000)
    struct.pack_into("<II", data, 0xb0, 0x40, 4 * len(caps))
    struct.pack_into(f"<{len(caps)}I", data, 0xc0, *caps)
    return bytes(data)


class MetadataTests(unittest.TestCase):
    def test_compatible_descriptor(self):
        validate_process_descriptor(descriptor())

    def test_rejects_original_boot_failure(self):
        with self.assertRaisesRegex(ValueError, "reserved debug bits"):
            validate_process_descriptor(descriptor(0x8ffff))

    def test_rejects_truncated_capabilities(self):
        with self.assertRaisesRegex(ValueError, "ACI section"):
            validate_process_descriptor(descriptor()[:-4])
