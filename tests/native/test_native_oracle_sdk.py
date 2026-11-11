import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import native_oracle_sdk


class NativeOracleSdkTests(unittest.TestCase):
    def test_x86_64_linux_uses_the_arch_specific_sdk(self):
        self.assertEqual(native_oracle_sdk.sdk_path(ROOT, "Linux", "x86_64"),
                         ROOT / ".audit/native-oracle/tools/dotnet-8.0.425-linux-x64/dotnet")

    def test_aarch64_linux_keeps_the_legacy_sdk_path(self):
        self.assertEqual(native_oracle_sdk.sdk_path(ROOT, "Linux", "aarch64"),
                         ROOT / ".audit/native-oracle/tools/dotnet-8.0.425/dotnet")

    def test_x64_selection_does_not_fall_back_to_an_existing_legacy_sdk(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as directory:
            root = Path(directory)
            legacy = root / ".audit/native-oracle/tools/dotnet-8.0.425/dotnet"
            legacy.parent.mkdir(parents=True)
            legacy.write_bytes(b"legacy arm64 sdk")
            self.assertNotEqual(native_oracle_sdk.sdk_path(root, "Linux", "x86_64"), legacy)

    def test_default_platform_detection_selects_the_host_sdk(self):
        with patch.object(native_oracle_sdk.platform, "system", return_value="Linux"), \
             patch.object(native_oracle_sdk.platform, "machine", return_value="x86_64"):
            self.assertEqual(native_oracle_sdk.sdk_path(ROOT),
                             ROOT / ".audit/native-oracle/tools/dotnet-8.0.425-linux-x64/dotnet")

    def test_non_linux_host_is_rejected_early(self):
        with self.assertRaisesRegex(RuntimeError, "Unsupported host OS.*Darwin"):
            native_oracle_sdk.sdk_path(ROOT, "Darwin", "x86_64")

    def test_unknown_linux_architecture_is_rejected_early(self):
        with self.assertRaisesRegex(RuntimeError, "Unsupported host architecture.*riscv64"):
            native_oracle_sdk.sdk_path(ROOT, "Linux", "riscv64")


if __name__ == "__main__":
    unittest.main()
