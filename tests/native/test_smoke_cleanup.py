import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "scripts"))
from smoke_native_room import X11, main, KEYBOARD_MAPPING


class SmokeCleanupTests(unittest.TestCase):
    def test_guest_phase_timeout_releases_owned_key_before_runtime_termination(self):
        self.check_timeout_cleanup(False)

    def test_post_jump_startup_allows_input_before_image_and_preserves_cleanup(self):
        self.check_timeout_cleanup(True)

    def test_post_climb_startup_allows_input_before_image_and_preserves_cleanup(self):
        self.check_timeout_cleanup(True, after_climb=True)

    def check_timeout_cleanup(self, after_wall_jump, after_climb=False):
        directory = ROOT / ".audit/native-room-vita/wrapper-correction-tests"
        directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            root = Path(temporary)
            fs, output, config, vpk = root / "state", root / "output", root / "config.yml", root / "synthetic.vpk"
            (fs / "ux0/app").mkdir(parents=True)
            (fs / "ux0/data").mkdir()
            config.write_text("backend-renderer: OpenGL\nresolution-multiplier: 1\ndisable-surface-sync: false\n")
            with config.open("a") as stream:
                stream.write("".join(f"keyboard-button-{button}: {key}\n" for button, key in KEYBOARD_MAPPING.items()))
            member = "assets/native-room/provenance.json"
            payload = json.dumps({"revision":"synthetic","tracked_changes":False}).encode()
            with zipfile.ZipFile(vpk,"w") as package:
                package.writestr(member,payload)
            order, held = [], set()
            x = X11.__new__(X11)
            x.display, x.fd, x.errors, x.keys, x.trace = None, 42, [], set(), []
            x.focused = lambda window: True
            x.activate = lambda window: None
            x.windows = Mock(side_effect=[[],[{"id":100,"name":"CELR00001 | OpenGL","pid":[424242]}]])
            def keymap(display,data):
                for code in held:
                    data[code//8] |= 1<<(code%8)
                return 1
            def inject(display,code,pressed,delay):
                order.append(("inject",code,pressed))
                held.add(code) if pressed else held.discard(code)
                return 1
            x.x = SimpleNamespace(XPending=lambda display:0,XQueryKeymap=keymap,XFlush=lambda display:None,
                XSync=lambda display,discard:None,XSelectInput=lambda *args:None,
                XCloseDisplay=lambda display:order.append(("display-close",)))
            x.xt = SimpleNamespace(XTestFakeKeyEvent=inject)
            class Process:
                def __init__(self,label,pid): self.label,self.pid,self.returncode=label,pid,None
                def terminate(self): order.append(("terminate",self.label)); self.returncode=-15
                def wait(self,timeout=None): return self.returncode
            installer, runtime = Process("installer",101), Process("runtime",102)
            def start(*args,**kwargs):
                if not (fs / "ux0/app/CELR00001").exists():
                    destination = fs / "ux0/app/CELR00001" / member
                    destination.parent.mkdir(parents=True)
                    destination.write_bytes(payload)
                    return installer
                return runtime
            def notify_read(*args):
                (fs / "ux0/data/celeste_native_room.ready").write_text("ready frame=0\n")
                return b"synthetic readiness event"
            original_read = Path.read_bytes
            def read_bytes(path):
                if str(path)=="/proc/424242/cmdline": return str(config.parent).encode()
                return original_read(path)
            libc = SimpleNamespace(inotify_init1=Mock(return_value=55),inotify_add_watch=Mock(return_value=1))
            arguments = ["smoke_native_room.py","--state",str(fs),"--output",str(output),"--vpk",str(vpk)]
            if after_wall_jump:
                arguments.append("--after-climb" if after_climb else "--after-wall-jump")
            with patch("sys.argv",arguments), \
                 patch("smoke_native_room.prepare",return_value=(fs,config)), patch("smoke_native_room.X11",return_value=x), \
                 patch("smoke_native_room.C.CDLL",return_value=libc), patch("smoke_native_room.subprocess.Popen",side_effect=start), \
                 patch("smoke_native_room.os.pidfd_open",side_effect=[201,202]), patch("smoke_native_room.os.close"), \
                 patch("smoke_native_room.os.read",side_effect=notify_read), patch.object(Path,"read_bytes",read_bytes), \
                 patch("smoke_native_room.collect_native_frame",return_value=None if after_wall_jump else {"artifacts":{},"black_letterbox_rows":True,"nonzero_rgb_bytes":1}), \
                 patch("smoke_native_room.select.select",side_effect=[([55],[],[]),TimeoutError("synthetic guest phase timeout")]):
                with self.assertRaisesRegex(TimeoutError,"synthetic guest phase timeout"):
                    main()
            code = 113 if after_wall_jump else 53
            self.assertEqual([item for item in order if item[0]=="inject"],[("inject",code,True),("inject",code,False)])
            self.assertLess(order.index(("inject",code,False)),order.index(("display-close",)))
            self.assertLess(order.index(("display-close",)),order.index(("terminate","runtime")))
            self.assertEqual(x.keys,set())
            self.assertEqual(held,set())
            feedback = json.loads((output / "feedback.json").read_text())
            self.assertTrue(feedback["stages"]["startup"])
            self.assertEqual(feedback["stages"]["native_image"],not after_wall_jump)
