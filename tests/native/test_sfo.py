from pathlib import Path
import struct
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / "scripts"))
from sfo import parse_sfo


def synthetic_sfo(kind=0x204, value=b"SYNTH0001\0", duplicate=False):
    key = b"TITLE_ID\0"
    count = 2 if duplicate else 1
    header = struct.pack("<5I",0x46535000,0x101,20+count*16,20+count*16+len(key),count)
    entry = struct.pack("<HHIII",0,kind,len(value),len(value),0)
    return header+entry*count+key+value


class SfoTests(unittest.TestCase):
    def test_string_metadata(self):
        self.assertEqual(parse_sfo(synthetic_sfo()),{"TITLE_ID":"SYNTH0001"})

    def test_integer_metadata(self):
        self.assertEqual(parse_sfo(synthetic_sfo(0x404,struct.pack("<I",42))),{"TITLE_ID":42})

    def test_duplicate_key_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"Duplicate SFO key"):
            parse_sfo(synthetic_sfo(duplicate=True))

    def test_invalid_header_or_entry_parameterized(self):
        original = synthetic_sfo()
        for bad in (b"",b"BAD!"+original[4:],original[:-1],original[:28]+struct.pack("<I",100)+original[32:]):
            with self.subTest(bad=bad):
                with self.assertRaises((ValueError,struct.error)):
                    parse_sfo(bad)
