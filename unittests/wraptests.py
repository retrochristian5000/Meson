# SPDX-License-Identifier: Apache-2.0
"""Wrap-file checksum and parsing consistency regressions.

A parent source updater can change a wrap between two filesystem reads.
Meson must never pair revision metadata from one read with the checksum of
another; QEMU's pinned DTC reconciliation uses the same invariant.
"""

import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mesonbuild.wrap.wrap import PackageDefinition


class WrapSnapshotTests(unittest.TestCase):
    def test_parsing_and_hashing_use_one_snapshot(self):
        first = (
            "[wrap-git]\n"
            "url = https://example.invalid/dtc.git\n"
            "revision = " + "a" * 40 + "\n"
            "depth = 1\n"
        )
        second = first.replace("a" * 40, "b" * 40)
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "dtc.wrap"
            filename.write_text(first, encoding="utf-8")
            normal_open = open
            reads = []

            def changing_open(path, mode="r", **kwargs):
                if str(path) == str(filename) and mode == "r":
                    reads.append(path)
                    return io.StringIO(first if len(reads) == 1 else second)
                return normal_open(path, mode, **kwargs)

            with mock.patch("mesonbuild.wrap.wrap.open",
                            side_effect=changing_open, create=True):
                wrap = PackageDefinition.from_wrap_file(str(filename))
            self.assertEqual(len(reads), 1)
            self.assertEqual(wrap.get("revision"), "a" * 40)
            self.assertEqual(wrap.wrapfile_hash,
                             hashlib.sha256(first.encode("utf-8")).hexdigest())

    def test_crlf_checksum_matches_mesons_normalized_text(self):
        original = (
            "[wrap-git]\n"
            "url = https://example.invalid/dtc.git\n"
            "revision = " + "c" * 40 + "\n"
            "depth = 1\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "dtc.wrap"
            filename.write_bytes(original.replace("\n", "\r\n").encode("utf-8"))
            wrap = PackageDefinition.from_wrap_file(str(filename))
            self.assertEqual(wrap.get("revision"), "c" * 40)
            self.assertEqual(wrap.wrapfile_hash,
                             hashlib.sha256(original.encode("utf-8")).hexdigest())
            self.assertNotEqual(wrap.wrapfile_hash,
                                hashlib.sha256(filename.read_bytes()).hexdigest())

    def test_wrap_change_produces_a_different_digest(self):
        original = (
            "[wrap-git]\n"
            "url = https://example.invalid/dtc.git\n"
            "revision = " + "d" * 40 + "\n"
            "depth = 1\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "dtc.wrap"
            filename.write_text(original, encoding="utf-8")
            first = PackageDefinition.from_wrap_file(str(filename))
            filename.write_text(original.replace("d" * 40, "e" * 40),
                                encoding="utf-8")
            second = PackageDefinition.from_wrap_file(str(filename))
            self.assertNotEqual(first.wrapfile_hash, second.wrapfile_hash)
            self.assertEqual(second.get("revision"), "e" * 40)


if __name__ == "__main__":
    unittest.main()
