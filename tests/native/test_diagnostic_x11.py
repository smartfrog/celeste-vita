from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / "scripts"))
from smoke_native_room import X11


class X11InputTests(unittest.TestCase):
    def test_preheld_key_is_not_injected_or_owned_or_released(self):
        injections = []
        x = X11.__new__(X11)
        x.display, x.fd, x.errors, x.keys, x.trace = None, 42, [], set(), []
        x.focused = lambda window: True
        def keymap(display, data):
            data[53//8] = 1<<(53%8)
            return 1
        x.x = SimpleNamespace(XFlush=lambda display: None, XSync=lambda display,discard: None,
                              XQueryKeymap=keymap, XPending=lambda display: 0, XCloseDisplay=lambda display: None)
        x.xt = SimpleNamespace(XTestFakeKeyEvent=lambda display,code,pressed,delay: injections.append((code,pressed)) or 1)
        try:
            with self.assertRaisesRegex(RuntimeError,"already held"):
                x.key(100,53,True)
        finally:
            x.close()
        self.assertEqual(injections,[])
        self.assertEqual(x.keys,set())

    def test_already_buffered_acknowledgement_does_not_block_on_fd(self):
        buffered, applied = [], []
        x = X11.__new__(X11)
        x.display, x.fd, x.errors, x.keys, x.trace = None, 42, [], set(), []
        x.focused = lambda window: True
        x.drain = lambda: (buffered.clear(), applied.append(True))
        def keymap(display,data):
            if applied:
                data[53//8] = 1<<(53%8)
            return 1
        def inject(*args):
            buffered.append(True)
            return 1
        x.x = SimpleNamespace(XFlush=lambda display: None, XSync=lambda display,discard: None,
                              XQueryKeymap=keymap, XPending=lambda display: len(buffered))
        x.xt = SimpleNamespace(XTestFakeKeyEvent=inject)
        with patch("smoke_native_room.select.select",side_effect=AssertionError("Buffered Xlib event must be drained before select")):
            x.key(100,53,True)
        self.assertEqual(x.keys,{53})

    def test_asynchronous_server_key_acknowledgement_is_event_driven(self):
        applied = []
        x = X11.__new__(X11)
        x.display, x.fd, x.errors, x.keys, x.trace = None, 42, [], set(), []
        x.focused = lambda window: True
        x.drain = lambda: applied.append(True)
        def keymap(display, data):
            if applied:
                data[53//8] = 1<<(53%8)
            return 1
        x.x = SimpleNamespace(XFlush=lambda display: None, XSync=lambda display,discard: None, XQueryKeymap=keymap,
                              XPending=lambda display: 0)
        x.xt = SimpleNamespace(XTestFakeKeyEvent=lambda *args: 1)
        with patch("smoke_native_room.select.select",return_value=([42],[],[])) as wait:
            x.key(100,53,True)
        self.assertEqual(wait.call_count,1)
        self.assertEqual(x.keys,{53})

    def test_accepted_injection_timeout_remains_owned_until_cleanup(self):
        injections = []
        x = X11.__new__(X11)
        x.display, x.fd, x.errors, x.keys, x.trace = None, 42, [], set(), []
        x.focused = lambda window: True
        x.x = SimpleNamespace(XFlush=lambda display: None, XSync=lambda display,discard: None,
                              XQueryKeymap=lambda display,data: 1, XPending=lambda display: 0,
                              XCloseDisplay=lambda display: None)
        x.xt = SimpleNamespace(XTestFakeKeyEvent=lambda display,code,pressed,delay: injections.append((code,pressed)) or 1)
        with patch("smoke_native_room.select.select",return_value=([],[],[])), patch("smoke_native_room.time.monotonic",side_effect=[0,11,11,11,11]):
            with self.assertRaisesRegex(RuntimeError,"within 10 seconds"):
                x.key(100,53,True)
        self.assertEqual(x.keys,{53})
        x.close()
        self.assertEqual(injections,[(53,True),(53,False)])
        self.assertEqual(x.keys,set())

    def test_unverified_focus_rejects_input_before_xtest(self):
        x = X11.__new__(X11)
        x.focused = lambda window: False
        with self.assertRaisesRegex(RuntimeError,"focus is unverified"):
            x.key(100,53,True)

    def test_rejected_injection_does_not_claim_key_ownership(self):
        x = X11.__new__(X11)
        x.display, x.fd, x.errors, x.keys, x.trace = None, 42, [], set(), []
        x.focused = lambda window: True
        x.x = SimpleNamespace(XQueryKeymap=lambda display,data: 1,XPending=lambda display: 0)
        x.xt = SimpleNamespace(XTestFakeKeyEvent=lambda *args: 0)
        with self.assertRaisesRegex(RuntimeError,"XTest key event failed"):
            x.key(100,53,True)
        self.assertEqual(x.keys,set())

    def test_release_of_unowned_key_is_rejected(self):
        x = X11.__new__(X11)
        x.display, x.fd, x.errors, x.keys, x.trace = None, 42, [], set(), []
        x.focused = lambda window: True
        x.x = SimpleNamespace(XQueryKeymap=lambda display,data: 1,XPending=lambda display: 0)
        with self.assertRaisesRegex(RuntimeError,"not owned"):
            x.key(100,53,False)
