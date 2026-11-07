import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import bootstrap_native_oracle as bootstrap


SDK = b"test-sdk"
SHA512 = "84a4d017d74d7aa842e981679d1b044e6be1f35b9b2b214021e30bc40871d016d29611cca373d8502ad5c890e3ad360ee698f9cf2d7a4d5a9fba102d88ba310f"


class SizedChunk:
    def __init__(self, size):
        self.size = size

    def __len__(self):
        return self.size


class OracleBootstrapTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / ".audit/native-validation-tests"
        directory.mkdir(parents=True, exist_ok=True)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.tools = Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=directory)))
        self.archive = self.tools / "dotnet-sdk-8.0.425-linux-arm64.tar.gz"
        self.metadata = self.release_metadata(SDK)
        self.archive_bytes = SDK
        self.stack.enter_context(patch.object(bootstrap, "TOOLS", self.tools))
        self.stack.enter_context(patch.object(bootstrap, "ARCHIVE_BYTES", len(SDK), create=True))
        self.stack.enter_context(patch.object(bootstrap, "ARCHIVE_SHA512", hashlib.sha512(SDK).hexdigest(), create=True))
        self.stack.enter_context(patch.object(bootstrap, "METADATA_BYTES", 4096, create=True))
        self.requests = self.stack.enter_context(patch.object(bootstrap.urllib.request, "urlopen", side_effect=self.response))
        self.extract = self.stack.enter_context(patch.object(bootstrap.tarfile, "open"))
        self.execute = self.stack.enter_context(patch.object(bootstrap.subprocess, "check_output", return_value="8.0.425\n"))
        self.stack.enter_context(patch("builtins.print"))

    def release_metadata(self, archive):
        return json.dumps({"releases": [{"sdks": [{"version": "8.0.425", "runtime-version": "8.0.31",
            "files": [{"rid": "linux-arm64", "url": "https://example.invalid/sdk", "hash": hashlib.sha512(archive).hexdigest()}]}]}]}).encode()

    def response(self, url, **kwargs):
        return io.BytesIO(self.metadata if url == bootstrap.METADATA else self.archive_bytes)

    def assert_no_install(self):
        self.extract.assert_not_called()
        self.execute.assert_not_called()
        self.assertEqual(list(self.tools.glob("*.part")), [])

    def test_metadata_size_exceed_is_rejected_before_archive_request(self):
        self.archive.write_bytes(SDK)
        limit = len(self.metadata)
        self.metadata += b" "
        with patch.object(bootstrap, "METADATA_BYTES", limit, create=True):
            with self.assertRaisesRegex(RuntimeError, "metadata.*(limit|size)|Metadata.*(limit|size)"):
                bootstrap.main()
        self.assertEqual(self.requests.call_count, 1)
        self.assertEqual(self.archive.read_bytes(), SDK)
        self.assert_no_install()

    def test_oversized_metadata_chunk_is_rejected_without_large_allocation(self):
        response = Mock()
        response.read.return_value = SizedChunk(2 * 1024 * 1024 + 1)
        with patch.object(bootstrap, "METADATA_BYTES", 2 * 1024 * 1024):
            with self.assertRaisesRegex(RuntimeError, "metadata.*limit"):
                bootstrap.read_metadata(response)
        self.assertEqual(response.read.call_args.args, (1024 * 1024,))

    def test_reviewer_oversized_archive_is_rejected_without_disk_or_large_allocation(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = SizedChunk(230686720)
        output = Mock()
        output.__enter__ = Mock(return_value=output)
        output.__exit__ = Mock(return_value=False)
        output.name = str(self.tools / "owned-download.part")
        with patch.object(bootstrap, "ARCHIVE_BYTES", 212188361), \
             patch.object(bootstrap.urllib.request, "urlopen", side_effect=[io.BytesIO(self.metadata), response]), \
             patch("tempfile.NamedTemporaryFile", return_value=output), \
             patch.object(bootstrap.hashlib, "file_digest") as digest:
            with self.assertRaisesRegex(RuntimeError, "size exceeds pinned 212188361"):
                bootstrap.main()
        output.write.assert_not_called()
        digest.assert_not_called()
        self.assertEqual(response.read.call_args.args, (1024 * 1024,))
        self.assert_no_install()

    def test_metadata_exact_limit_is_accepted(self):
        with patch.object(bootstrap, "METADATA_BYTES", len(self.metadata), create=True):
            bootstrap.main()
        self.assertEqual(self.archive.read_bytes(), SDK)

    def test_archive_size_exceed_is_rejected_before_extraction(self):
        self.archive_bytes = SDK + b"!"
        self.metadata = self.release_metadata(self.archive_bytes)
        with patch.object(bootstrap, "ARCHIVE_SHA512", hashlib.sha512(self.archive_bytes).hexdigest(), create=True):
            with self.assertRaisesRegex(RuntimeError, "(size|exceed)"):
                bootstrap.main()
        self.assertFalse(self.archive.exists())
        self.assert_no_install()

    def test_premature_archive_eof_is_rejected_before_extraction(self):
        self.archive_bytes = SDK[:-1]
        self.metadata = self.release_metadata(self.archive_bytes)
        with patch.object(bootstrap, "ARCHIVE_SHA512", hashlib.sha512(self.archive_bytes).hexdigest(), create=True):
            with self.assertRaisesRegex(RuntimeError, "(size|short|EOF)"):
                bootstrap.main()
        self.assertFalse(self.archive.exists())
        self.assert_no_install()

    def test_exact_archive_is_verified_and_promoted(self):
        bootstrap.main()
        self.assertEqual(self.archive.read_bytes(), SDK)
        self.assertEqual(list(self.tools.glob("*.part")), [])
        self.extract.assert_called_once()
        self.execute.assert_called_once()
        receipt = json.loads((self.tools / "sdk-verification.json").read_text())
        self.assertEqual(receipt["sha512"], hashlib.sha512(SDK).hexdigest())

    def test_small_chunk_streams_reach_exact_archive_boundary(self):
        with patch.object(bootstrap, "CHUNK_BYTES", 3):
            bootstrap.main()
        self.assertEqual(self.archive.read_bytes(), SDK)

    def test_existing_cache_wrong_size_parameterized(self):
        for contents in [SDK[:-1], SDK + b"!"]:
            with self.subTest(size=len(contents)):
                self.archive.write_bytes(contents)
                with self.assertRaisesRegex(RuntimeError, "size"):
                    bootstrap.main()
                self.assertEqual(self.archive.read_bytes(), contents)
                self.assert_no_install()

    def test_existing_verified_cache_is_preserved(self):
        self.archive.write_bytes(SDK)
        bootstrap.main()
        self.assertEqual(self.archive.read_bytes(), SDK)
        self.assertEqual(self.requests.call_count, 1)

    def test_existing_cache_wrong_hash_is_preserved(self):
        contents = b"bad-data"
        self.archive.write_bytes(contents)
        with self.assertRaisesRegex(RuntimeError, "SHA512"):
            bootstrap.main()
        self.assertEqual(self.archive.read_bytes(), contents)
        self.assert_no_install()

    def test_download_wrong_hash_cleans_only_owned_partial(self):
        self.archive_bytes = b"bad-data"
        unrelated = self.tools / "unrelated.keep"
        unrelated.write_bytes(b"preserve")
        with self.assertRaisesRegex(RuntimeError, "SHA512"):
            bootstrap.main()
        self.assertFalse(self.archive.exists())
        self.assertEqual(unrelated.read_bytes(), b"preserve")
        self.assert_no_install()

    def test_network_failure_cleans_partial(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.side_effect = [b"test", OSError("synthetic disconnect")]
        with patch.object(bootstrap.urllib.request, "urlopen", side_effect=[io.BytesIO(self.metadata), response]):
            with self.assertRaisesRegex(OSError, "synthetic disconnect"):
                bootstrap.main()
        self.assertFalse(self.archive.exists())
        self.assert_no_install()

    def test_changed_published_hash_is_rejected_without_touching_cache(self):
        self.archive.write_bytes(SDK)
        self.metadata = self.release_metadata(b"different")
        with self.assertRaisesRegex(RuntimeError, "metadata.*SHA512|published.*SHA512"):
            bootstrap.main()
        self.assertEqual(self.archive.read_bytes(), SDK)
        self.assertEqual(self.requests.call_count, 1)
        self.assert_no_install()


class PinnedArtifactTests(unittest.TestCase):
    def test_published_archive_size_is_pinned(self):
        self.assertEqual(getattr(bootstrap, "ARCHIVE_BYTES", None), 212188361)

    def test_published_archive_sha512_is_pinned(self):
        self.assertEqual(getattr(bootstrap, "ARCHIVE_SHA512", None), SHA512)


if __name__ == "__main__":
    unittest.main()
