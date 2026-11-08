from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / "scripts"))
from smoke_native_room import X11


class X11InputTests(unittest.TestCase):
    def test_asynchronous_server_key_acknowledgement_is_event_driven(self):
        applied = []
        x = X11.__new__(X11)
        x.display, x.fd, x.errors, x.keys = None, 42, [], set()
        x.focused = lambda window: True
        x.drain = lambda: applied.append(True)
        def keymap(display, data):
            if applied:
                data[53//8] = 1<<(53%8)
            return 1
        x.x = SimpleNamespace(XFlush=lambda display: None, XSync=lambda display,discard: None, XQueryKeymap=keymap)
        x.xt = SimpleNamespace(XTestFakeKeyEvent=lambda *args: 1)
        with patch("smoke_native_room.select.select",return_value=([42],[],[])) as wait:
            x.key(100,53,True)
        self.assertEqual(wait.call_count,1)
        self.assertEqual(x.keys,{53})

    def test_unverified_focus_rejects_input_before_xtest(self):
        x = X11.__new__(X11)
        x.focused = lambda window: False
        with self.assertRaisesRegex(RuntimeError,"focus is unverified"):
            x.key(100,53,True)
