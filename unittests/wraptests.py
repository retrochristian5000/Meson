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

from mesonbuild.wrap.wrap import PackageDefinition, Resolver, WrapException
from mesonbuild.wrap import WrapMode


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


class ExistingPatchDirectoryTests(unittest.TestCase):
    def make_source(self, root):
        subprojects = root / 'subprojects'
        subprojects.mkdir()
        patch = subprojects / 'packagefiles' / 'softfloat'
        patch.mkdir(parents=True)
        (patch / 'meson.build').write_text("project('softfloat', 'c')\\n",
                                           encoding='utf-8')
        (patch / 'meson_options.txt').write_text(
            "option('defines', type: 'array', value: [])\\n",
            encoding='utf-8')
        (subprojects / 'softfloat.wrap').write_text(
            "[wrap-git]\\n"
            "url = https://example.invalid/softfloat.git\\n"
            "revision = " + "a" * 40 + "\\n"
            "patch_directory = softfloat\\n",
            encoding='utf-8')
        checkout = subprojects / 'softfloat'
        checkout.mkdir()
        (checkout / 'source').mkdir()
        (checkout / 'source' / 'original.c').write_text(
            '/* keep the original source */\\n', encoding='utf-8')
        return checkout

    def test_existing_checkout_restores_missing_build_definition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = self.make_source(root)
            resolver = Resolver(str(root), 'subprojects',
                                wrap_mode=WrapMode.nodownload)
            path, method = resolver.resolve('softfloat')
            self.assertEqual(path, 'subprojects/softfloat')
            self.assertEqual(method, 'meson')
            self.assertTrue((checkout / 'meson.build').is_file())
            self.assertTrue((checkout / 'meson_options.txt').is_file())
            self.assertEqual(
                (checkout / 'source' / 'original.c').read_text(),
                '/* keep the original source */\\n')
            marker = checkout / '.meson-subproject-wrap-hash.txt'
            self.assertTrue(marker.is_file())
            self.assertEqual(marker.read_text().strip(),
                             resolver.wrap.wrapfile_hash)
            # Re-resolving does not reapply or mutate an existing project.
            again = Resolver(str(root), 'subprojects',
                             wrap_mode=WrapMode.nodownload)
            self.assertEqual(again.resolve('softfloat'), (path, method))

    def test_existing_patch_conflict_preserves_all_source_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = self.make_source(root)
            option = checkout / 'meson_options.txt'
            option.write_text('custom local options\\n', encoding='utf-8')
            resolver = Resolver(str(root), 'subprojects',
                                wrap_mode=WrapMode.nodownload)
            with self.assertRaisesRegex(WrapException,
                                        'preserving local changes'):
                resolver.resolve('softfloat')
            self.assertEqual(option.read_text(), 'custom local options\\n')
            self.assertFalse((checkout / 'meson.build').exists())
            self.assertFalse(
                (checkout / '.meson-subproject-wrap-hash.txt').exists())
            self.assertEqual(
                (checkout / 'source' / 'original.c').read_text(),
                '/* keep the original source */\\n')


if __name__ == "__main__":
    unittest.main()
