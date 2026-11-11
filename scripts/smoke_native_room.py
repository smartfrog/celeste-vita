#!/usr/bin/env python3
"""Bounded manual-X11 or explicit guest-replay smoke; never capture screens."""

import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import re
import select
import subprocess
import time
import zipfile

from vita_room_emulator import TITLE, prepare, launch_command, launcher_kind
from native_room_feedback import collect_native_frame, native_capture_policy, new_feedback, save_feedback
from native_room_revision import REPO_ROOT
from native_room_replay import (verify_replay_intent, verify_replay_guest, completion_receipt, verify_replay_source,
                                verify_automatic_intent, verify_automatic_guest, verify_automatic_source,
                                verify_dash_probe_source)
from native_room_dash_runtime import verify_dash_probe_intent, verify_dash_probe_guest, dash_probe_completion_receipt

KEYBOARD_MAPPING = {"left":"ArrowLeft", "up":"ArrowUp", "right":"ArrowRight", "cross":"KeyX", "square":"KeyZ", "triangle":"KeyV", "start":"Enter", "l1":"KeyQ", "l2":"KeyU"}


def verify_keyboard_mapping(text):
    lines = text.splitlines()
    for button, key in KEYBOARD_MAPPING.items():
        if [line for line in lines if line.startswith("keyboard-button-"+button+":")] != ["keyboard-button-"+button+": "+key]:
            raise ValueError("Isolated keyboard mapping differs for "+button)


def verify_no_owned_runtime(state):
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal() or int(entry.name) == os.getpid():
            continue
        try:
            arguments = (entry / "cmdline").read_bytes().split(b"\0")
        except FileNotFoundError:
            continue
        if arguments and Path(os.fsdecode(arguments[0])).name in {"Vita3K", "bwrap"} and any(os.fsencode(state) in arg for arg in arguments):
            raise RuntimeError("An emulator already owns this private state; refusing duplicate runtime")


def verify_guest(text, revision, initial_resets=0):
    markers = [f"DIAGNOSTIC boot revision={revision} fixed_step=1/60", "assets ready", "frame ready",
               "cross_held=1 cross_pressed=1", "cross_held=0 cross_pressed=0", "square_held=1 square_pressed=1",
               "from=0 to=2 freeze=0.050000001 dashes=0", "from=1 to=0 state=2",
               "dir_x=0.000000 dir_y=-1.000000 vx=0.000 vy=-240.000", "from=2 to=0 freeze=0.000000000",
               "death frame=", "manual reset frame=", "clean exit frame="]
    offset = 0
    for marker in markers:
        offset = text.index(marker,offset)+len(marker)
    if "FATAL" in text or " x=1 y=0 " not in text:
        raise ValueError("Completed guest log lacks right input or reports an error")
    jump = re.search(r"frame frame=\d+ x=19 y=(\d+) vx=0\.000 vy=(-[\d.]+) ground=\d dead=0 resets="+str(initial_resets),text)
    death = re.search(r"death frame=\d+ x=(\d+) y=\d+ .* dead=1 resets="+str(initial_resets),text)
    if not jump or int(jump[1]) >= 144 or not death or int(death[1]) <= 19:
        raise ValueError("Completed log does not prove jump/right movement/actual death")
    for marker in ("manual reset", "clean exit"):
        if not re.search(marker+r" frame=\d+ x=19 y=144 .* dead=0 resets="+str(initial_resets+1),text):
            raise ValueError("Completed guest reset/exit state is not fresh")
    return markers


def verify_wall_jump_guest(text):
    jump = re.search(r"jump frame=(\d+) x=([\d.]+) y=([\d.]+) vx=130\.000 vy=-105\.000 ground=0 dead=0 resets=0 .* "
                     r"move_x=-1 force_x=1 force_timer=0\.159999996 var_timer=0\.200000003 jump_buffer=0\.000000000 jump_kind=WallJump",text)
    forced = re.search(r"wall forced frame=(\d+) x=([\d.]+) .* move_x=1 force_x=1 .* jump_kind=WallJump",text)
    if not jump or not forced or int(forced[1]) <= int(jump[1]) or float(forced[2]) <= float(jump[2]):
        raise ValueError("Completed log lacks actual WallJump launch/buffer/timers and forced-right movement")
    return {"jump_frame":int(jump[1]),"forced_frame":int(forced[1]),"x":float(jump[2]),"y":float(jump[3])}


def verify_climb_guest(text):
    states = []
    offset = 0
    for event in ("entered", "drained", "held", "released", "landed"):
        match = re.search(r"climb "+event+r" frame=(\d+) (.+)", text[offset:])
        if not match:
            raise ValueError("Missing actual Climb "+event+" checkpoint")
        values = dict(field.split("=",1) for field in match[2].split())
        values["frame"] = int(match[1])
        states.append(values)
        offset += match.end()
    entered, drained, held, released, landed = states
    if not (all(a["frame"] < b["frame"] for a,b in zip(states, states[1:])) and
            all(row["dead"] == "0" and row["resets"] == "0" for row in states) and
            entered["state"] == drained["state"] == held["state"] == "1" and
            entered["grab"] == drained["grab"] == held["grab"] == "1" and drained["ground"] == "0" and
            float(drained["y"]) < float(entered["y"]) and 0 < float(held["stamina"]) < float(drained["stamina"]) < 110 and
            released["state"] == "0" and released["grab"] == "0" and landed["ground"] == "1" and float(landed["stamina"]) == 110):
        raise ValueError("Climb log lacks actual airborne ascent/drain/hold/release/landing proof")
    return states


class XError(C.Structure):
    _fields_ = [("type",C.c_int),("display",C.c_void_p),("resource",C.c_ulong),("serial",C.c_ulong),
                ("code",C.c_ubyte),("request",C.c_ubyte),("minor",C.c_ubyte)]


class ClientMessage(C.Structure):
    _fields_ = [("type",C.c_int),("serial",C.c_ulong),("send_event",C.c_int),("display",C.c_void_p),
                ("window",C.c_ulong),("message_type",C.c_ulong),("format",C.c_int),("data",C.c_long*5)]


class KeyEvent(C.Structure):
    _fields_ = [("type",C.c_int),("serial",C.c_ulong),("send_event",C.c_int),("display",C.c_void_p),
                ("window",C.c_ulong),("root",C.c_ulong),("subwindow",C.c_ulong),("time",C.c_ulong),
                ("x",C.c_int),("y",C.c_int),("x_root",C.c_int),("y_root",C.c_int),
                ("state",C.c_uint),("keycode",C.c_uint),("same_screen",C.c_int)]


class X11:
    def __init__(self):
        self.x = C.CDLL("libX11.so.6")
        self.xt = C.CDLL("libXtst.so.6")
        signatures = {
            "XOpenDisplay": (C.c_void_p, [C.c_char_p]), "XDefaultRootWindow": (C.c_ulong, [C.c_void_p]),
            "XConnectionNumber": (C.c_int, [C.c_void_p]), "XInternAtom": (C.c_ulong, [C.c_void_p,C.c_char_p,C.c_int]),
            "XQueryTree": (C.c_int, [C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)]),
            "XFetchName": (C.c_int, [C.c_void_p,C.c_ulong,C.POINTER(C.c_char_p)]),
            "XGetWindowProperty": (C.c_int, [C.c_void_p,C.c_ulong,C.c_ulong,C.c_long,C.c_long,C.c_int,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.c_void_p)]),
            "XGetInputFocus": (C.c_int, [C.c_void_p,C.POINTER(C.c_ulong),C.POINTER(C.c_int)]),
            "XSetInputFocus": (C.c_int, [C.c_void_p,C.c_ulong,C.c_int,C.c_ulong]),
            "XRaiseWindow": (C.c_int, [C.c_void_p,C.c_ulong]), "XSelectInput": (C.c_int, [C.c_void_p,C.c_ulong,C.c_long]),
            "XPending": (C.c_int,[C.c_void_p]), "XNextEvent": (C.c_int,[C.c_void_p,C.c_void_p]),
            "XFlush": (C.c_int,[C.c_void_p]), "XSync": (C.c_int,[C.c_void_p,C.c_int]),
            "XFree": (C.c_int,[C.c_void_p]), "XCloseDisplay": (C.c_int,[C.c_void_p]),
            "XQueryKeymap": (C.c_int,[C.c_void_p,C.c_void_p]),
            "XSendEvent": (C.c_int,[C.c_void_p,C.c_ulong,C.c_int,C.c_long,C.c_void_p]),
        }
        for name, (result, arguments) in signatures.items():
            f = getattr(self.x,name)
            f.restype, f.argtypes = result, arguments
        self.xt.XTestFakeKeyEvent.argtypes = [C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
        self.xt.XTestFakeKeyEvent.restype = C.c_int
        self.display = self.x.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError("Cannot open the existing X11 display")
        self.errors = []
        handler = C.CFUNCTYPE(C.c_int,C.c_void_p,C.POINTER(XError))
        self.error_handler = handler(lambda display,error: self.errors.append((error.contents.code,error.contents.request)) or 0)
        self.x.XSetErrorHandler.argtypes = [handler]
        self.x.XSetErrorHandler(self.error_handler)
        self.root = self.x.XDefaultRootWindow(self.display)
        self.fd = self.x.XConnectionNumber(self.display)
        self.x.XSelectInput(self.display,self.root,(1<<19)|(1<<22))
        self.keys = set()
        self.trace = []

    def property(self, window, name):
        atom = self.x.XInternAtom(self.display,name.encode(),False)
        actual, fmt, count, remaining, data = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong(), C.c_void_p()
        result = self.x.XGetWindowProperty(self.display,window,atom,0,32,False,0,C.byref(actual),C.byref(fmt),C.byref(count),C.byref(remaining),C.byref(data))
        if result or not data.value:
            return []
        try:
            return list(C.cast(data,C.POINTER(C.c_ulong))[:count.value]) if fmt.value == 32 else []
        finally:
            self.x.XFree(data)

    def name(self, window):
        name = C.c_char_p()
        if not self.x.XFetchName(self.display,window,C.byref(name)) or not name.value:
            return ""
        try:
            return name.value.decode(errors="replace")
        finally:
            self.x.XFree(C.cast(name,C.c_void_p))

    def windows(self, parent=None, depth=0):
        root, owner, children, count = C.c_ulong(), C.c_ulong(), C.POINTER(C.c_ulong)(), C.c_uint()
        if depth > 5 or not self.x.XQueryTree(self.display,parent or self.root,C.byref(root),C.byref(owner),C.byref(children),C.byref(count)):
            return []
        try:
            ids = list(children[:count.value])
        finally:
            if children:
                self.x.XFree(children)
        found = []
        for window in ids:
            name = self.name(window)
            if name:
                found.append({"id":window,"name":name,"pid":self.property(window,"_NET_WM_PID")})
            found.extend(self.windows(window,depth+1))
        return found

    def focused(self, window):
        focus, revert = C.c_ulong(), C.c_int()
        self.x.XGetInputFocus(self.display,C.byref(focus),C.byref(revert))
        return focus.value == window and self.property(self.root,"_NET_ACTIVE_WINDOW") == [window]

    def activate(self, window):
        event = (C.c_long*24)()
        message = C.cast(event,C.POINTER(ClientMessage)).contents
        message.type, message.send_event, message.display, message.window = 33, True, self.display, window
        message.message_type = self.x.XInternAtom(self.display,b"_NET_ACTIVE_WINDOW",False)
        message.format, message.data[0] = 32, 2
        if not self.x.XSendEvent(self.display,self.root,False,(1<<20)|(1<<19),event):
            raise RuntimeError("Cannot request activation of OUR game window")
        self.x.XRaiseWindow(self.display,window)
        self.x.XSetInputFocus(self.display,window,2,0)
        self.x.XFlush(self.display)

    def drain(self):
        events = []
        while self.x.XPending(self.display):
            event = (C.c_long*24)()
            self.x.XNextEvent(self.display,event)
            key = C.cast(event,C.POINTER(KeyEvent)).contents
            observed = {"type":key.type,"window":key.window}
            if key.type in (2,3):
                observed.update({"keycode":key.keycode,"modifiers":key.state})
            events.append(observed)
        if events:
            self.trace.append({"phase":"drained-events","events":events})

    def key_state(self, phase, code, pressed):
        keymap = (C.c_ubyte*32)()
        self.x.XQueryKeymap(self.display,keymap)
        pending = self.x.XPending(self.display)
        held = bool(keymap[code//8] & (1<<(code%8)))
        self.trace.append({"phase":phase,"keycode":code,"requested_pressed":pressed,"server_pressed":held,
                           "pending_xlib_events":pending,"keymap_hex":bytes(keymap).hex(),"xerrors":list(self.errors)})
        if any(error != 3 for error,request in self.errors):
            raise RuntimeError(f"X11 request failed: {self.errors}")
        return held

    def await_key_state(self, code, pressed):
        deadline = time.monotonic()+10
        while True:
            if self.x.XPending(self.display):
                self.drain()
            if self.key_state("acknowledgement",code,pressed) == pressed:
                return
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                self.key_state("timeout",code,pressed)
                raise RuntimeError("XTest did not establish the requested server key state within 10 seconds")
            if self.x.XPending(self.display):
                continue
            if select.select([self.fd],[],[],remaining)[0]:
                self.drain()

    def key(self, window, code, pressed):
        if not self.focused(window):
            raise RuntimeError("OUR window focus is unverified; refusing input")
        held = self.key_state("before-injection",code,pressed)
        if pressed and held:
            raise RuntimeError(f"Key {code} is already held; refusing unowned input")
        if not pressed and code not in self.keys:
            raise RuntimeError(f"Key {code} is not owned; refusing release")
        accepted = bool(self.xt.XTestFakeKeyEvent(self.display,code,pressed,0))
        self.trace.append({"phase":"injection","keycode":code,"pressed":pressed,"accepted":accepted})
        if not accepted:
            raise RuntimeError("XTest key event failed")
        if pressed:
            self.keys.add(code)
        self.x.XFlush(self.display)
        self.x.XSync(self.display,False)
        self.await_key_state(code,pressed)
        if not pressed:
            self.keys.remove(code)

    def close(self):
        failures = []
        try:
            for code in tuple(self.keys):
                try:
                    self.key_state("before-cleanup-release",code,False)
                except RuntimeError as error:
                    failures.append(str(error))
                try:
                    accepted = bool(self.xt.XTestFakeKeyEvent(self.display,code,False,0))
                    self.trace.append({"phase":"cleanup-release","keycode":code,"accepted":accepted})
                    if not accepted:
                        raise RuntimeError(f"XTest cleanup release failed for owned key {code}")
                    self.x.XSync(self.display,False)
                    self.await_key_state(code,False)
                    self.keys.remove(code)
                except RuntimeError as error:
                    failures.append(str(error))
        finally:
            self.x.XCloseDisplay(self.display)
        if failures:
            raise RuntimeError("Owned input cleanup failed: " + "; ".join(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vpk", type=Path, required=True)
    parser.add_argument("--existing", type=Path, default=Path("/home/fred/cloudpunk-vita/tools/vita3k"))
    parser.add_argument("--appdir", type=Path, help="Extracted AppDir; default is <existing>/squashfs-root")
    parser.add_argument("--source-checkout", type=Path, default=REPO_ROOT,
                        help="Clean VPK-source checkout for guest replay; default is this source root")
    parser.add_argument("--feedback",type=Path)
    parser.add_argument("--frame-only",action="store_true")
    guest_mode = parser.add_mutually_exclusive_group()
    guest_mode.add_argument("--guest-replay",action="store_true",help="Use only the compiled legacy guest-controls fixture; no X11/input/portal calls")
    guest_mode.add_argument("--guest-automatic",action="store_true",help="Verify the production automatic lifecycle using input-only guest controls")
    guest_mode.add_argument("--guest-dash-probe",action="store_true",help="Verify the source-bound native Dash GPU probe using guest-only controls")
    parser.add_argument("--source-root",type=Path,help="Native source root providing authoritative automatic VPK verification")
    parser.add_argument("--expected-source-state",type=Path,help="Explicit exact-WIP native manifest; absent retains strict clean verification")
    parser.add_argument("--build",type=Path,help="Native build src/vita directory for authoritative VPK verification")
    parser.add_argument("--staging",type=Path,help="Native staged payload for authoritative VPK verification")
    capture = parser.add_mutually_exclusive_group()
    capture.add_argument("--after-wall-jump",action="store_true")
    capture.add_argument("--after-climb",action="store_true")
    args = parser.parse_args()
    if args.frame_only and (args.after_wall_jump or args.after_climb):
        parser.error("Post-WallJump capture requires input")
    if args.guest_replay and (args.frame_only or not args.after_climb):
        parser.error("Guest replay requires --after-climb and cannot use --frame-only")
    if args.guest_dash_probe:
        if args.frame_only or args.after_climb or args.after_wall_jump:
            parser.error("Guest Dash probe cannot use manual/deferred capture modes")
        if not all((args.source_root, args.build, args.staging)):
            parser.error("Guest Dash probe requires --source-root, --build and --staging")
    if args.guest_automatic and (args.frame_only or args.after_climb or args.after_wall_jump):
        parser.error("Guest automatic cannot use manual/deferred capture modes")
    if args.guest_automatic and not all((args.source_root, args.build, args.staging)):
        parser.error("Guest automatic requires --source-root, --build and --staging")
    if args.expected_source_state and not ((args.guest_automatic or args.guest_dash_probe) and args.source_root):
        parser.error("Expected source state requires --guest-automatic or --guest-dash-probe and --source-root")
    scripted_guest = args.guest_replay or args.guest_automatic or args.guest_dash_probe
    state, output, existing = args.state.resolve(), args.output.resolve(), args.existing.resolve()
    appdir = (args.appdir or existing / "squashfs-root").resolve()
    if not output.is_relative_to(REPO_ROOT / ".audit/native-room-vita"):
        parser.error("Evidence must remain beneath .audit/native-room-vita")
    output.mkdir(parents=True,exist_ok=False)
    feedback_path = (args.feedback or output / "feedback.json").resolve()
    feedback = json.loads(feedback_path.read_text()) if feedback_path.is_file() else new_feedback(None,args.vpk.resolve())
    if args.guest_dash_probe and (feedback.get('frame') or feedback.get('artifacts') or
            any(feedback['stages'].get(key) for key in ('native_image','input','clean_exit','full_completion'))):
        raise ValueError('Dash requires fresh runtime feedback, not earlier frame/completion evidence')
    with zipfile.ZipFile(args.vpk) as package:
        installed = {name:package.read(name) for name in package.namelist()}
    provenance = json.loads(installed["assets/native-room/provenance.json"])
    capture_policy = native_capture_policy(provenance.get("render_style") == "animated_player_partial",
                                           bool(provenance.get("guest_replay")),args.after_wall_jump,args.after_climb,
                                           dash_probe=args.guest_dash_probe)
    feedback["capture_policy"] = capture_policy
    revision = provenance.get("binding", {}).get("revision_label") or provenance["revision"] + ("-dirty" if provenance["tracked_changes"] else "")
    verify_automatic_intent(provenance,args.guest_automatic)
    verify_dash_probe_intent(provenance,args.guest_dash_probe)
    actual_hash = hashlib.sha256(args.vpk.read_bytes()).hexdigest()
    if feedback["vpk"]["sha256"] is not None and feedback["vpk"]["sha256"] != actual_hash:
        raise ValueError("VPK changed after package verification")
    feedback["vpk"]["sha256"] = actual_hash
    if scripted_guest:
        feedback.update(requested_scope="guest_dash_probe_smoke" if args.guest_dash_probe else "guest_automatic_smoke" if args.guest_automatic else "guest_replay_smoke",input_source="scripted_guest_controls",
                        physical_controller_verified=False,host_input_injected=False,portal_requests=0)
        if args.guest_automatic:
            def automatic_source():
                selected = verify_automatic_source(provenance,args.vpk.resolve(),args.source_root.resolve(),
                                                   args.build.resolve(),args.staging.resolve(),
                                                   args.expected_source_state.resolve() if args.expected_source_state else None)
                if selected["package"]["vpk_sha256"] != actual_hash:
                    raise ValueError("Automatic VPK changed after its initial input pin")
                if capture_policy != "initial_respawn" or selected["package"].get("build_binding",{}).get("capture_policy") != capture_policy:
                    raise ValueError("Automatic VPK lacks the exact bound initial_respawn capture policy")
                return selected
            feedback["guest_automatic_provenance"] = automatic_source()
            feedback["guest_automatic"] = provenance["guest_automatic"]
            feedback["stages"]["package_verified"] = True
        elif args.guest_dash_probe:
            def dash_source():
                selected = verify_dash_probe_source(provenance,args.vpk.resolve(),args.source_root.resolve(),
                                                    args.build.resolve(),args.staging.resolve(),
                                                    args.expected_source_state.resolve() if args.expected_source_state else None)
                if selected['package']['vpk_sha256']!=actual_hash or selected['package'].get('build_binding',{}).get('capture_policy')!='dash_trails':
                    raise ValueError('Dash VPK changed or lacks its resident capture policy')
                return selected
            feedback['guest_dash_probe_provenance'] = dash_source()
            feedback['guest_dash_probe'] = provenance['guest_dash_probe']
            feedback['stages']['package_verified'] = True
        else:
            feedback["guest_replay_provenance"] = verify_replay_source(provenance,args.source_checkout.resolve())
            feedback["guest_replay"] = provenance["guest_replay"]
        verify_no_owned_runtime(state)
    else:
        verify_replay_intent(provenance,False)
    feedback["revision"] = revision
    launcher_kind(appdir)
    fs, config = prepare(state,existing)
    if args.guest_dash_probe:
        basename = f'celeste_native_room-{revision}-dash-probe.ppm'
        names = ['celeste_native_room.log','celeste_native_room.ready',basename,basename+'.txt',basename+'.trail.rgba',
                 f'celeste_native_room-complete-{revision}-dash-probe.txt',f'celeste_native_room-failure-{revision}-dash-probe.txt']
        if any((fs / 'ux0/data' / name).exists() or (fs / 'ux0/data' / name).is_symlink() for name in names):
            raise ValueError('Dash requires fresh guest log/readiness/export/completion/failure paths; prior evidence preserved')
    if not scripted_guest:
        verify_keyboard_mapping(config.read_text())
    frozen_config = output / "effective-config.yml"
    frozen_config.write_bytes(config.read_bytes())
    feedback["emulator_config"] = {"path":str(config),"frozen_path":str(frozen_config),
                                  "sha256":hashlib.sha256(frozen_config.read_bytes()).hexdigest(),
                                  "backend":"OpenGL","resolution_multiplier":1,"disable_surface_sync":False,
                                   "override_scope":"fresh private state only; shared config untouched"}
    if not scripted_guest:
        feedback["emulator_config"]["verified_keyboard_mapping"] = KEYBOARD_MAPPING
    save_feedback(feedback_path,feedback)
    if (fs / "ux0/app" / TITLE).exists():
        parser.error("Use a fresh isolated state; never overwrite an installed title")
    x = None if scripted_guest else X11()
    inventory = [] if x is None else x.windows()
    if x is not None:
        (output / "windows-before.json").write_text(json.dumps(inventory,indent=2)+"\n")
    if any(TITLE in window["name"] or "Celeste Native Room Diagnostic" in window["name"] for window in inventory):
        x.close()
        raise RuntimeError("Diagnostic window already exists; ownership ambiguous")
    notify = None
    if x is not None:
        libc = C.CDLL(None,use_errno=True)
        libc.inotify_init1.argtypes, libc.inotify_init1.restype = [C.c_int], C.c_int
        libc.inotify_add_watch.argtypes, libc.inotify_add_watch.restype = [C.c_int,C.c_char_p,C.c_uint32], C.c_int
        notify = libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
        if notify < 0 or libc.inotify_add_watch(notify,os.fsencode(fs / "ux0/data"),0x8|0x80) < 0:
            raise OSError(C.get_errno(),"inotify initialization failed")
    command, env = launch_command(state,existing,["-c",str(config.parent),"--keep-config","--",str(args.vpk.resolve())],
                                  appdir,readonly_paths=[args.vpk.resolve()],unshare_pid=scripted_guest)
    events = [{"host_input_api":"not_created","window_inventory":"not_requested","host_input_injected":False,"portal_requests":0}] if scripted_guest else []
    process = None
    process_fd = None
    ready = fs / "ux0/data/celeste_native_room.ready"
    last_ready = ""
    frame_only_complete = False
    automatic_verified = False
    dash_verified = False
    mode_suffix = '-dash-probe' if args.guest_dash_probe else ''
    failure = fs / 'ux0/data' / f'celeste_native_room-failure-{revision}{mode_suffix}.txt'
    export_basename = f'celeste_native_room-{revision}' + ('-dash-probe.ppm' if args.guest_dash_probe else '.ppm')

    def observe_native_frame():
        if not feedback["stages"]["native_image"]:
            guest = fs / "ux0/data/celeste_native_room.log"
            skipped = f"capture_skipped_existing path=ux0:data/{export_basename} "
            if guest.exists() and any(line.startswith(skipped) and "current_run_capture=false" in line
                                      for line in guest.read_text().splitlines()):
                return
            if scripted_guest:
                marker = f"frame_saved path=ux0:data/{export_basename} "
                if not guest.exists() or not any(line.startswith(marker) and line.endswith("\n") for line in guest.read_text().splitlines(keepends=True)):
                    return
            if capture_policy == "initial_respawn" and (not guest.exists() or
                    [line for line in guest.read_text().splitlines() if line.startswith("capture policy=")] != ["capture policy=initial_respawn"]):
                raise ValueError("Guest lacks its exact initial_respawn capture policy receipt")
            frame = collect_native_frame(fs,output,revision,capture=capture_policy,
                                         visual_provenance=provenance.get("visuals") if provenance.get("render_style") in {"textured_partial", "animated_player_partial"} else None,
                                         player_provenance=provenance.get("player"),
                                         decal_provenance=provenance.get("decals"))
            if frame:
                frame["vpk_sha256"] = feedback["vpk"]["sha256"]
                feedback.update({"frame":frame,"artifacts":frame["artifacts"]})
                feedback["stages"].update({"native_image":True,"image_openable":True})
                save_feedback(feedback_path,feedback)
                print("NATIVE_FRAME_FEEDBACK "+str(feedback_path),flush=True)
                if (not args.guest_dash_probe and not frame["black_letterbox_rows"]) or not frame["nonzero_rgb_bytes"]:
                    raise RuntimeError("Native frame export lacks nonzero room RGB or the full-frame black letterbox rows; inspect preserved readback")
                feedback["stages"]["render_content"] = True
                save_feedback(feedback_path,feedback)

    def wait(predicate, timeout=120):
        nonlocal last_ready
        deadline = time.monotonic()+timeout
        while True:
            if scripted_guest:
                if failure.exists() or failure.is_symlink():
                    raise RuntimeError('Guest failure receipt present: '+str(failure))
                guest_log = fs / "ux0/data/celeste_native_room.log"
                if guest_log.exists() and "FATAL:" in guest_log.read_text():
                    raise RuntimeError("Guest reported FATAL; see preserved guest.log")
                if ready.exists():
                    value = ready.read_text()
                    if value != last_ready:
                        last_ready = value
                        events.append({"readiness_only":value.strip(),"at":time.monotonic()})
                    observe_native_frame()
            if x is not None and x.x.XPending(x.display):
                x.drain()
            if predicate():
                return
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Bounded guest/readiness wait expired")
            if x is not None and x.x.XPending(x.display):
                continue
            descriptors = [process_fd] if scripted_guest else [x.fd,notify,process_fd]
            readable,_,_ = select.select(descriptors,[],[],min(remaining,0.25) if scripted_guest else remaining)
            if process_fd in readable:
                if scripted_guest and predicate():
                    return
                raise RuntimeError(f"Owned emulator exited before smoke completion: {process.wait()}")
            if x is not None and x.fd in readable:
                x.drain()
            if notify is not None and notify in readable:
                os.read(notify,65536)
                if ready.exists():
                    value = ready.read_text()
                    if value != last_ready:
                        last_ready = value
                        events.append({"readiness_only":value.strip(),"at":time.monotonic()})
                    observe_native_frame()
                    if value.startswith("failed "):
                        raise RuntimeError("Guest failed: "+failure.read_text())

    def delay(seconds):
        deadline = time.monotonic()+seconds
        wait(lambda: time.monotonic() >= deadline,seconds+0.1)

    try:
        with (output / "install-host.log").open("wb") as host:
            process = subprocess.Popen(command,env=env,cwd=state,stdout=host,stderr=subprocess.STDOUT)
            process_fd = os.pidfd_open(process.pid)
            events.append({"installer_pid":process.pid,"command":command})
            wait(lambda: all((fs / "ux0/app" / TITLE / name).is_file() and
                             (fs / "ux0/app" / TITLE / name).read_bytes() == data for name,data in installed.items()),30)
            process.terminate()
            process.wait(timeout=15)
            os.close(process_fd)
            process_fd = None
            events.append({"installed_exact_vpk_entries":True,"stopped_owned_installer":True})
        runtime_arguments = ["-c",str(config.parent),"--keep-config"] + \
                            (["--frontend","sdl"] if scripted_guest else []) + ["-r",TITLE]
        command, env = launch_command(state,existing,runtime_arguments,appdir,unshare_pid=scripted_guest)
        with (output / "host.log").open("wb") as host:
            process = subprocess.Popen(command,env=env,cwd=state,stdout=host,stderr=subprocess.STDOUT)
            process_fd = os.pidfd_open(process.pid)
            events.append({"runtime_pid":process.pid,"command":command})
            if scripted_guest:
                wait(lambda: bool(last_ready),150)
                feedback["stages"]["startup"] = True
                save_feedback(feedback_path,feedback)
                complete = fs / "ux0/data" / f"celeste_native_room-complete-{revision}{mode_suffix}.txt"
                def completed():
                    if not complete.exists():
                        return False
                    if args.guest_dash_probe and complete.is_symlink():
                        raise ValueError('Dash completion must be an owned regular file')
                    expected = dash_probe_completion_receipt(revision,provenance['guest_dash_probe_fixture']) if args.guest_dash_probe else completion_receipt(revision,automatic=args.guest_automatic)
                    if (args.guest_dash_probe and complete.stat().st_size>1024) or complete.read_text() != expected:
                        raise ValueError("Guest completion receipt differs from the exact replay contract")
                    return True
                wait(completed,420)
                observe_native_frame()
                receipt = output / "guest-complete.txt"
                receipt.write_bytes(complete.read_bytes())
                events.append({"closed_guest_completion":str(receipt),"host_input_injected":False,"portal_requests":0})
            else:
                window = None

                def find_window():
                    nonlocal window
                    matches = []
                    for candidate in x.windows():
                        if TITLE not in candidate["name"] or "OpenGL" not in candidate["name"] or not candidate["pid"]:
                            continue
                        try:
                            command_line = Path(f'/proc/{candidate["pid"][0]}/cmdline').read_bytes()
                        except FileNotFoundError:
                            continue
                        if str(config.parent).encode() in command_line:
                            matches.append(candidate)
                    if len(matches) > 1:
                        raise RuntimeError("Ambiguous diagnostic game windows")
                    if not matches:
                        return False
                    window = matches[0]
                    return True

                wait(find_window)
                events.append({"game_window":window})
                wid = window["id"]
                wait(lambda: last_ready.startswith("ready "))
                observe_native_frame()
                feedback["stages"]["startup"] = True
                save_feedback(feedback_path,feedback)
                if capture_policy == "initial_respawn" and not feedback["stages"]["native_image"]:
                    wait(lambda: feedback["stages"]["native_image"],120)
                elif capture_policy == "spawn" and not feedback["stages"]["native_image"]:
                    raise RuntimeError("Guest startup ready without its required closed native frame export")
                if args.frame_only:
                    frame_only_complete = True
                    events.append({"frame_only_checkpoint":True,"input_not_attempted":True,"guest_clean_exit_not_claimed":True})
                    return
                x.x.XSelectInput(x.display,wid,(1<<0)|(1<<1)|(1<<21)|(1<<22))
                x.activate(wid)
                wait(lambda: x.focused(wid),10)

                def inject(code,pressed):
                    x.key(wid,code,pressed)
                    events.append({"injected_keycode":code,"pressed":pressed,"focus_and_server_key_state_verified":True})

                def change(code,pressed,expected="sampled"):
                    before = last_ready
                    inject(code,pressed)
                    wait(lambda: last_ready != before and last_ready.startswith(expected+" "),30)

                if args.after_wall_jump:
                    change(113,True)
                    inject(53,True)
                    wait(lambda: last_ready.startswith("wall_near "),30)
                    change(53,False)
                    inject(53,True)
                    wait(lambda: last_ready.startswith("wall_forced ") and feedback["stages"]["native_image"],30)
                    change(53,False)
                    change(113,False)
                    change(55,True,"reset")
                    change(55,False)

                if args.after_climb:
                    change(113,True)
                    inject(53,True)
                    wait(lambda: last_ready.startswith("wall_near "),30)
                    change(53,False)
                    wait(lambda: last_ready.startswith("climb_near "),30)
                    change(24,True,"climb_entered")
                    change(113,False)
                    inject(111,True)
                    wait(lambda: last_ready.startswith("climb_drained ") and feedback["stages"]["native_image"],60)
                    change(111,False)
                    wait(lambda: last_ready.startswith("climb_held "),30)
                    change(24,False,"climb_released")
                    wait(lambda: last_ready.startswith("climb_landed "),60)
                    change(55,True,"reset")
                    change(55,False)

                change(53,True)
                delay(0.25)
                change(53,False)
                delay(1.0)
                change(111,True)
                change(52,True)
                change(52,False)
                wait(lambda: last_ready.startswith("dash_done "),120)
                change(111,False)
                change(114,True)
                wait(lambda: last_ready.startswith("dead "),60)
                change(114,False)
                change(55,True,"reset")
                change(55,False)
                x.key(wid,36,True)
            host_wait_error = None
            try:
                status = process.wait(timeout=30)
            except subprocess.TimeoutExpired as error:
                host_wait_error = error
                status = None
                events.append({"owned_host_pending_after_guest_exit":True})
            events.append({"host_exit_code":status})
        guest = fs / "ux0/data/celeste_native_room.log"
        data = guest.read_bytes()
        (output / "guest.log").write_bytes(data)
        text = data.decode()
        if args.guest_automatic:
            proof = verify_automatic_guest(text,revision,provenance["guest_automatic"],provenance["guest_automatic_fixture"])
            feedback["guest_automatic_observed"] = proof
            markers = proof["markers"]
            if feedback["stages"]["native_image"]:
                frame = feedback["frame"]
                if frame["capture"] != "initial_respawn" or frame["frame_state"]["frame"] != proof["respawn_normal_frames"][0]+1:
                    raise ValueError("Initial Respawn capture is not the first observed Normal app frame")
        elif args.guest_dash_probe:
            proof = verify_dash_probe_guest(text,revision,provenance['guest_dash_probe_fixture'],complete.read_text(),feedback.get('frame'))
            feedback['guest_dash_probe_observed'] = proof
            markers = proof['markers']
        elif args.guest_replay:
            proof = verify_replay_guest(text,revision,provenance["guest_replay"],args.source_checkout.resolve())
            feedback["guest_replay_observed"] = proof
            markers = proof["markers"]
        else:
            markers = verify_guest(text,revision,initial_resets=1 if args.after_wall_jump or args.after_climb else 0)
        if args.after_wall_jump:
            feedback["wall_jump"] = verify_wall_jump_guest(text)
        if args.after_climb:
            feedback["climb"] = verify_climb_guest(text)
        feedback["stages"].update({"input":True,"clean_exit":True})
        if scripted_guest:
            if not feedback["stages"]["native_image"]:
                raise RuntimeError("Completed guest replay lacks its current-run closed native frame")
            if status is None:
                raise TimeoutError("Owned emulator did not exit within 30 seconds after guest completion") from host_wait_error
            if status != 0:
                raise RuntimeError(f"Owned emulator failed after guest completion: {status}")
        if args.guest_automatic:
            automatic_verified = True
        elif args.guest_dash_probe:
            dash_verified = True
        else:
            feedback["stages"]["full_completion"] = True
        save_feedback(feedback_path,feedback)
        events.append({"completed_guest_markers":markers,"claim":"Diagnostic only; not full game or hardware proof"})
    except Exception as error:
        feedback["stages"]["full_completion"] = False
        feedback["errors"].append({"stage":"runtime","type":type(error).__name__,"message":str(error)})
        save_feedback(feedback_path,feedback)
        raise
    finally:
        try:
            if x is not None:
                x.close()
        except Exception as error:
            feedback["errors"].append({"stage":"owned_input_cleanup","type":type(error).__name__,"message":str(error)})
            feedback["stages"]["full_completion"] = False
            raise
        finally:
            if notify is not None:
                os.close(notify)
            if process_fd is not None:
                os.close(process_fd)
            try:
                if process is not None and process.returncode is None:
                    process.terminate()
                    process.wait(timeout=15)
                    events.append({"stopped_owned_host_after_frame_checkpoint" if frame_only_complete else
                                   "stopped_owned_host_after_guest_exit" if feedback["stages"]["clean_exit"] else "stopped_owned_host_on_failure":True,
                                   "host_exit_code":process.returncode})
            except Exception as error:
                feedback["errors"].append({"stage":"owned_process_cleanup","type":type(error).__name__,"message":str(error)})
                feedback["stages"]["full_completion"] = False
                raise
            finally:
                guest = fs / "ux0/data/celeste_native_room.log"
                if guest.is_file():
                    (output / "guest.log").write_bytes(guest.read_bytes())
                (output / "x11-input.json").write_text(json.dumps([] if x is None else x.trace,indent=2)+"\n")
                (output / "events.json").write_text(json.dumps(events,indent=2)+"\n")
                feedback["runtime_evidence"] = {"events":str(output / "events.json"),"x11_input":str(output / "x11-input.json"),
                                                "host":str(output / "host.log"),"guest":str(output / "guest.log")}
                feedback["emulator_config"]["sha256_after"] = hashlib.sha256(config.read_bytes()).hexdigest()
                config_changed = scripted_guest and feedback["emulator_config"]["sha256_after"] != feedback["emulator_config"]["sha256"]
                if config_changed:
                    feedback["stages"]["full_completion"] = False
                    feedback["errors"].append({"stage":"config_after","type":"RuntimeError","message":"Private emulator config changed during replay"})
                failure_error = None
                if scripted_guest:
                    try:
                        try:
                            failure.lstat()
                        except FileNotFoundError:
                            if not failure.parent.is_dir():
                                raise RuntimeError('Cannot verify guest failure absence: '+str(failure.parent))
                        else:
                            raise RuntimeError('Guest failure receipt present after owned process cleanup: '+str(failure))
                    except (OSError,RuntimeError) as error:
                        failure_error = error
                        feedback['stages']['full_completion'] = False
                        feedback['errors'].append(dict(stage='guest_failure_after',type=type(error).__name__,message=str(error)))
                if args.guest_dash_probe:
                    try:
                        after = dash_source()
                        feedback['guest_dash_probe_source_after'] = after
                        if after!=feedback['guest_dash_probe_provenance']:
                            raise ValueError('Dash source/inputs/artifacts/harness changed during runtime')
                        feedback['stages']['full_completion'] = dash_verified and not config_changed and not feedback['errors']
                    except Exception as error:
                        feedback['stages']['full_completion'] = False
                        feedback['errors'].append(dict(stage='source_after',type=type(error).__name__,message=str(error)))
                        save_feedback(feedback_path,feedback)
                        raise
                if args.guest_automatic:
                    try:
                        after = automatic_source()
                        feedback["guest_automatic_source_after"] = after
                        if after != feedback["guest_automatic_provenance"]:
                            raise ValueError("Automatic source/inputs/artifacts/harness changed during runtime")
                        feedback["stages"]["full_completion"] = automatic_verified and not config_changed and not feedback["errors"]
                    except Exception as error:
                        feedback["stages"]["full_completion"] = False
                        feedback["errors"].append({"stage":"source_after","type":type(error).__name__,"message":str(error)})
                        save_feedback(feedback_path,feedback)
                        raise
                save_feedback(feedback_path,feedback)
                if failure_error is not None:
                    raise failure_error
                if config_changed:
                    raise RuntimeError("Private emulator config changed during replay")


if __name__ == "__main__":
    main()
