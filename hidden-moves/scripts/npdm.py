"""Validate this module's NPDM subset against Eden 0.2.1's capability rules.

Reference: eden-emulator/mirror v0.2.1, k_capabilities.cpp and .h.
Reject unsupported capability types rather than silently accepting new ones.
"""

import struct


def validate_process_descriptor(data: bytes) -> None:
    if len(data) < 0x80 or data[:4] != b"META":
        raise ValueError("Invalid NPDM header")
    aci, size = struct.unpack_from("<II", data, 0x70)
    if size < 0x40 or aci + size > len(data) or data[aci:aci + 4] != b"ACI0":
        raise ValueError("Invalid NPDM ACI section")
    if struct.unpack_from("<Q", data, aci + 0x10)[0] != 0x0100000011D90000:
        raise ValueError("Generated process descriptor has the wrong program ID")
    offset, length = struct.unpack_from("<II", data, aci + 0x30)
    if offset < 0x40 or length % 4 or offset + length > size:
        raise ValueError("Invalid NPDM kernel capability range")
    seen = set()
    svc_groups = set()
    svcs = set()
    for (cap,) in struct.iter_unpack("<I", data[aci + offset:aci + offset + length]):
        if cap == 0xffffffff:
            continue
        kind = ((cap ^ (cap + 1)).bit_length() - 1)
        if kind not in (3, 4, 13, 14, 15, 16):
            raise ValueError(f"Unsupported NPDM kernel capability: {cap:#010x}")
        if kind != 4:
            if kind in seen:
                raise ValueError("Duplicate NPDM kernel capability")
            seen.add(kind)
        if kind == 3:
            low, high = (cap >> 4) & 63, (cap >> 10) & 63
            first, last = (cap >> 16) & 255, cap >> 24
            if not 4 <= high <= low or not first <= last < 4:
                raise ValueError("Invalid NPDM thread/core permissions")
        elif kind == 4:
            group = cap >> 29
            if group in svc_groups:
                raise ValueError("Duplicate NPDM syscall group")
            svc_groups.add(group)
            mask = (cap >> 5) & 0xffffff
            svcs.update(group * 24 + bit for bit in range(24) if mask & (1 << bit))
        elif kind == 13 and cap >> 17:
            raise ValueError("Reserved NPDM application-type bits")
        elif kind == 14 and cap >> 19 == 0:
            raise ValueError("Invalid NPDM kernel version")
        elif kind == 15 and cap >> 26:
            raise ValueError("Reserved NPDM handle-table bits")
        elif kind == 16 and cap >> 19:
            raise ValueError(f"Eden 0.2.1 rejects reserved debug bits: {cap:#010x}")
    if not {3, 13, 14, 15, 16} <= seen:
        raise ValueError("Missing NPDM process capabilities")
    if any(svc >= 0xc0 for svc in svcs):
        raise ValueError("NPDM syscall ID out of range")
    if not {0x08, 0x09, 0x21, 0x27, 0x40, 0x43, 0x74, 0x75} <= svcs:
        raise ValueError("Missing native hook syscall permissions")
