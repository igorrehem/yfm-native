#!/usr/bin/env python3
"""Test how tools/pc/check_mod_abi.py fetches a baseline release: only the
package whose sha256 tools/pc/mod_compat.txt pins is unpacked, the package is
kept beside the folder and checked again whenever the folder is used, a
folder without its package is fetched again, and a package holding a name
outside its folder is refused. Synthetic packages, served from a folder of
this test's through file:// URLs; nothing is downloaded or run."""
import hashlib, io, os, pathlib, sys, tarfile, tempfile, unittest, zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_mod_abi

TAG = "v9.9.9"
TOP = f"yfm-redecomp-{TAG}"
NAMES = {"windows": f"{TOP}-windows.zip", "linux": f"{TOP}-linux.tar.gz"}


def make_zip(path, members):
    with zipfile.ZipFile(path, "w") as package:
        for name, data in members.items():
            package.writestr(name, data)


def make_tar(path, members):
    with tarfile.open(path, "w:gz") as package:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            package.addfile(info, io.BytesIO(data))


def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


class Fetch(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="mod-compat-fetch-")
        base = self.scratch.name
        self.cache, self.server = os.path.join(base, "cache"), os.path.join(base, "server")
        os.makedirs(os.path.join(self.server, TAG))
        for name, value in (("CACHE", self.cache), ("DOWNLOADS", pathlib.Path(self.server).as_uri()),
                            ("print", lambda *arguments, **options: None)):
            patcher = mock.patch.object(check_mod_abi, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.scratch.cleanup)
        self.downloads = []
        real = check_mod_abi.urllib.request.urlopen

        def counting(url, *arguments, **options):
            self.downloads.append(url)
            return real(url, *arguments, **options)
        patcher = mock.patch.object(check_mod_abi.urllib.request, "urlopen", counting)
        patcher.start()
        self.addCleanup(patcher.stop)
        # fetch()'s waits for another run's package: none really, each one
        # counted and, when a test sets one, a step of that other run.
        self.waits, self.while_waiting = [], None

        def sleep(seconds):
            self.waits.append(seconds)
            if self.while_waiting:
                self.while_waiting()
        patcher = mock.patch.object(check_mod_abi, "time", mock.Mock(sleep=sleep))
        patcher.start()
        self.addCleanup(patcher.stop)

    def publish(self, system="windows", members=None):
        """A package on the test's server: {(TAG, system): its sha256}."""
        members = members or {f"{TOP}/sdk/exports.txt": b"Mod_Name\n", f"{TOP}/mods/a/mod.json": b"{}"}
        path = os.path.join(self.server, TAG, NAMES[system])
        (make_zip if system == "windows" else make_tar)(path, members)
        return {(TAG, system): digest(path)}

    def folder(self, system="windows"):
        return os.path.join(self.cache, TAG, system)

    def unpacked(self, system="windows"):
        return os.path.join(self.folder(system), "verified", TOP)

    def assert_only_kept(self, system="windows"):
        """Nothing of the fetch is left but the package and the folder unpacked from it."""
        self.assertEqual(sorted(os.listdir(self.folder(system))), sorted(["verified", NAMES[system]]))
        self.assertEqual(os.listdir(os.path.dirname(self.unpacked(system))), [TOP])

    def assert_nothing_kept(self, system="windows"):
        """No folder, no package, no staging."""
        self.assertLessEqual(set(os.listdir(self.folder(system))), {"verified"})
        self.assertFalse(os.path.exists(self.unpacked(system)))

    def refused(self, digests, system="windows"):
        with self.assertRaises(SystemExit) as caught:
            check_mod_abi.fetch(TAG, system, digests)
        return str(caught.exception.code)

    def test_pinned_package_is_unpacked_and_kept(self):
        for system in NAMES:
            with self.subTest(system=system):
                if system == "linux" and not hasattr(tarfile, "data_filter"):
                    self.skipTest("this Python's tarfile has no data filter "
                                  "(3.8.17+, 3.9.17+, 3.10.12+, 3.11.4+ or 3.12)")
                digests = self.publish(system)
                unpacked = check_mod_abi.fetch(TAG, system, digests)
                self.assertEqual(unpacked, self.unpacked(system))
                self.assertEqual(pathlib.Path(unpacked, "sdk", "exports.txt").read_bytes(), b"Mod_Name\n")
                kept = os.path.join(self.folder(system), NAMES[system])
                self.assertEqual(digest(kept), digests[(TAG, system)])
                # Nothing of the download is left but the folder and its package.
                self.assert_only_kept(system)

    def test_64bit_windows_package_is_unpacked_and_kept(self):
        """An x86_64-windows baseline's package: the .zip whose folder is
        yfm-redecomp-TAG-x64 (package.py), pinned like the others."""
        name, top = f"{TOP}-windows-x64.zip", f"{TOP}-x64"
        path = os.path.join(self.server, TAG, name)
        make_zip(path, {f"{top}/sdk/exports.x86_64-windows.txt": b"Mod_Name\n"})
        digests = {(TAG, "windows-x64"): digest(path)}
        unpacked = check_mod_abi.fetch(TAG, "windows-x64", digests)
        self.assertEqual(unpacked, os.path.join(self.folder("windows-x64"), "verified", top))
        self.assertEqual(sorted(os.listdir(self.folder("windows-x64"))), sorted(["verified", name]))
        self.assertIn("is not the", self.refused({(TAG, "windows-x64"): "0" * 64}, "windows-x64"))

    def test_other_package_is_refused_before_unpacking(self):
        for system in NAMES:
            with self.subTest(system=system):
                self.publish(system)
                message = self.refused({(TAG, system): "0" * 64}, system)
                self.assertIn("is not the", message)
                self.assertIn("0" * 64, message)
                self.assertIn("nothing of it was unpacked", message)
                self.assert_nothing_kept(system)

    def test_unpinned_release_is_refused(self):
        self.publish()
        message = self.refused({(TAG, "linux"): "0" * 64})
        self.assertIn(f"sha256 {TAG} windows", message)
        self.assertIn("gh api", message)
        self.assertEqual(self.downloads, [])

    def test_cached_folder_beside_its_package_is_used_without_download(self):
        digests = self.publish()
        check_mod_abi.fetch(TAG, "windows", digests)
        os.remove(os.path.join(self.server, TAG, NAMES["windows"]))   # a download now would fail
        self.downloads.clear()
        self.assertTrue(os.path.isdir(check_mod_abi.fetch(TAG, "windows", digests)))
        self.assertEqual(self.downloads, [])

    def test_cached_package_without_folder_is_unpacked_without_download(self):
        digests = self.publish()
        unpacked = check_mod_abi.fetch(TAG, "windows", digests)
        check_mod_abi.shutil.rmtree(unpacked)
        self.downloads.clear()
        self.assertTrue(os.path.isfile(os.path.join(check_mod_abi.fetch(TAG, "windows", digests), "sdk", "exports.txt")))
        self.assertEqual(self.downloads, [])

    def test_folder_without_package_is_fetched_again(self):
        digests = self.publish()
        stale = self.unpacked()
        os.makedirs(os.path.join(stale, "mods", "planted"))
        pathlib.Path(stale, "mods", "planted", "mod.json").write_text("{}")
        unpacked = check_mod_abi.fetch(TAG, "windows", digests)
        self.assertEqual(len(self.downloads), 1)
        self.assertFalse(os.path.exists(os.path.join(unpacked, "mods", "planted")))
        self.assertTrue(os.path.isfile(os.path.join(unpacked, "mods", "a", "mod.json")))
        self.assert_only_kept()

    def test_older_checks_folder_beside_the_package_is_not_used(self):
        # A check from before the pinning unpacks to <tag>/<system>/TOP, with no
        # hash check, even beside a verified package; that folder is never used.
        digests = self.publish()
        check_mod_abi.shutil.rmtree(check_mod_abi.fetch(TAG, "windows", digests))
        older = os.path.join(self.folder(), TOP)
        os.makedirs(os.path.join(older, "mods", "planted"))
        self.downloads.clear()
        unpacked = check_mod_abi.fetch(TAG, "windows", digests)
        self.assertEqual(unpacked, self.unpacked())
        self.assertFalse(os.path.exists(os.path.join(unpacked, "mods", "planted")))
        self.assertTrue(os.path.isfile(os.path.join(unpacked, "mods", "a", "mod.json")))
        self.assertEqual(self.downloads, [])

    def plant_before_move_in(self, digests, with_package):
        """fetch(), with a folder put in its place just before it moves its own
        in: by an older check (no package) or by another run (its package)."""
        real, unpacked, planted = os.rename, self.unpacked(), []

        def rename(source, target):
            if target == unpacked and not planted:
                planted.append(target)
                os.makedirs(os.path.join(unpacked, "mods", "planted"))
                if with_package:
                    check_mod_abi.shutil.copy(os.path.join(self.server, TAG, NAMES["windows"]), self.folder())
            return real(source, target)
        with mock.patch.object(check_mod_abi.os, "rename", rename):
            return check_mod_abi.fetch(TAG, "windows", digests)

    def test_folder_put_in_meanwhile_without_package_is_not_trusted(self):
        digests = self.publish()
        unpacked = self.plant_before_move_in(digests, with_package=False)
        self.assertFalse(os.path.exists(os.path.join(unpacked, "mods", "planted")))
        self.assertTrue(os.path.isfile(os.path.join(unpacked, "mods", "a", "mod.json")))
        self.assert_only_kept()

    def test_folder_put_in_meanwhile_beside_its_package_is_used(self):
        digests = self.publish()
        unpacked = self.plant_before_move_in(digests, with_package=True)
        self.assertTrue(os.path.isdir(os.path.join(unpacked, "mods", "planted")))   # the other run's
        self.assert_only_kept()

    def test_folder_whose_package_comes_while_waiting_is_used(self):
        # Another run fetching the same release has moved its folder in and
        # is about to move its package beside it: that folder is not evicted.
        digests = self.publish()
        os.makedirs(os.path.join(self.unpacked(), "mods", "planted"))
        package = os.path.join(self.server, TAG, NAMES["windows"])
        self.while_waiting = lambda: check_mod_abi.shutil.copy(package, self.folder())
        unpacked = check_mod_abi.fetch(TAG, "windows", digests)
        self.assertTrue(os.path.isdir(os.path.join(unpacked, "mods", "planted")))   # the other run's
        self.assertEqual(len(self.waits), 1)
        self.assert_only_kept()

    def test_folder_set_aside_while_waiting_is_replaced(self):
        digests = self.publish()
        stale = self.unpacked()
        os.makedirs(os.path.join(stale, "mods", "planted"))
        self.while_waiting = lambda: check_mod_abi.shutil.rmtree(stale, ignore_errors=True)   # by another run
        unpacked = check_mod_abi.fetch(TAG, "windows", digests)
        self.assertEqual(len(self.waits), 1)
        self.assertFalse(os.path.exists(os.path.join(unpacked, "mods", "planted")))
        self.assertTrue(os.path.isfile(os.path.join(unpacked, "mods", "a", "mod.json")))
        self.assert_only_kept()

    def test_folder_that_cannot_be_set_aside_is_refused(self):
        digests = self.publish()
        stale = self.unpacked()
        os.makedirs(os.path.join(stale, "mods", "planted"))
        real = os.rename

        def rename(source, target):
            if source == stale:
                raise PermissionError(13, "in use", source)
            return real(source, target)
        with mock.patch.object(check_mod_abi.os, "rename", rename):
            message = self.refused(digests)
        self.assertIn("cannot set aside", message)
        self.assertIn(f"delete {self.folder()}", message)
        self.assertEqual(len(self.waits), 10)
        # Nothing of this fetch is left, and the folder is still not trusted.
        self.assertEqual(os.listdir(self.folder()), ["verified"])
        self.assertTrue(os.path.isdir(os.path.join(stale, "mods", "planted")))

    def test_folder_another_run_set_aside_meanwhile_is_replaced(self):
        digests = self.publish()
        stale = self.unpacked()
        os.makedirs(os.path.join(stale, "mods", "planted"))
        real = os.rename

        def rename(source, target):
            if source == stale:   # another run moved it away first
                check_mod_abi.shutil.rmtree(stale)
                raise FileNotFoundError(2, "gone", source)
            return real(source, target)
        with mock.patch.object(check_mod_abi.os, "rename", rename):
            unpacked = check_mod_abi.fetch(TAG, "windows", digests)
        self.assertFalse(os.path.exists(os.path.join(unpacked, "mods", "planted")))
        self.assertTrue(os.path.isfile(os.path.join(unpacked, "mods", "a", "mod.json")))
        self.assert_only_kept()

    def test_changed_package_beside_folder_is_refused(self):
        digests = self.publish()
        check_mod_abi.fetch(TAG, "windows", digests)
        kept = os.path.join(self.folder(), NAMES["windows"])
        with open(kept, "ab") as handle:
            handle.write(b"\0")
        self.downloads.clear()
        message = self.refused(digests)
        self.assertIn(kept, message)
        self.assertIn("delete", message)
        self.assertEqual(self.downloads, [])

    def test_member_outside_the_folder_is_refused(self):
        for system in NAMES:
            for outside in ("../escape.txt", f"{TOP}/../escape.txt", "/absolute.txt", "other/file.txt",
                            "C:/drive.txt", f"{TOP}\\..\\escape.txt"):
                with self.subTest(system=system, member=outside):
                    digests = self.publish(system, {f"{TOP}/sdk/exports.txt": b"", outside: b"x"})
                    message = self.refused(digests, system)
                    self.assertIn("outside", message)
                    self.assert_nothing_kept(system)
                    self.assertFalse(os.path.exists(os.path.join(self.scratch.name, "escape.txt")))

    def test_link_out_of_the_folder_is_refused(self):
        # A name under the folder passes the name check; tarfile's data filter
        # refuses the link, and that is a message, not a traceback.
        if not hasattr(tarfile, "data_filter"):
            self.skipTest("this Python's tarfile has no data filter (3.8.17+, 3.9.17+, 3.10.12+, 3.11.4+ or 3.12)")
        path = os.path.join(self.server, TAG, NAMES["linux"])
        with tarfile.open(path, "w:gz") as package:
            info = tarfile.TarInfo(f"{TOP}/sdk")
            info.type = tarfile.DIRTYPE
            package.addfile(info)
            info = tarfile.TarInfo(f"{TOP}/sdk/escape")
            info.type, info.linkname = tarfile.SYMTYPE, "../../../escape.txt"
            package.addfile(info)
        message = self.refused({(TAG, "linux"): digest(path)}, "linux")
        self.assertIn("nothing of it was kept", message)
        self.assert_nothing_kept("linux")

    def test_package_without_its_folder_is_refused(self):
        digests = self.publish(members={f"{TOP}": b"a file, not the folder"})
        self.assertIn(f"no {TOP} folder", self.refused(digests))


class List(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as scratch:
            path = os.path.join(scratch, "mod_compat.txt")
            pathlib.Path(path).write_text(text, encoding="utf-8")
            with mock.patch.object(check_mod_abi, "LIST", path):
                return check_mod_abi.read_list()

    def test_sha256_lines(self):
        baselines, accepted, digests = self.read(f"baseline {TAG}\nsha256 {TAG} windows {'a' * 64}\n"
                                                 f"sha256 {TAG} linux {'b' * 64}  # the tarball\n")
        self.assertEqual(baselines, [(TAG, "i386")])
        self.assertEqual(digests, {(TAG, "windows"): "a" * 64, (TAG, "linux"): "b" * 64})

    def test_64bit_baseline_and_its_package(self):
        baselines, _, digests = self.read(f"baseline {TAG} x86_64-windows\nsha256 {TAG} windows-x64 {'c' * 64}\n")
        self.assertEqual(baselines, [(TAG, "x86_64-windows")])
        self.assertEqual(digests, {(TAG, "windows-x64"): "c" * 64})

    def test_malformed_sha256_lines(self):
        for line in (f"sha256 {TAG} windows {'a' * 63}", f"sha256 {TAG} windows {'A' * 64}",
                     f"sha256 {TAG} macos {'a' * 64}", f"sha256 {TAG} {'a' * 64}"):
            with self.subTest(line=line), self.assertRaises(SystemExit):
                self.read(line + "\n")

    def test_repository_list_pins_every_baseline(self):
        baselines, _, digests = check_mod_abi.read_list()
        for tag, target in baselines:
            for system in check_mod_abi.PACKAGES[target]:
                self.assertIn((tag, system), digests, f"mod_compat.txt: no `sha256 {tag} {system}`")


if __name__ == "__main__":
    unittest.main()
