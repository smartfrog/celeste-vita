#!/usr/bin/env python3
"""Bounded nonvisual X11 smoke for OUR isolated Vita3K title; never capture screens."""

import argparse
import ctypes as C
import json
import os
from pathlib import Path
import re
import select
import subprocess
import time
import zipfile

from vita_room_emulator import TITLE, prepare, launch_command


def verify_guest(text, revision):
    markers = [f"DIAGNOSTIC boot revision={revision} fixed_step=1/60", "assets ready", "frame ready",
               "cross_held=1 cross_pressed=1", "cross_held=0 cross_pressed=0", "death frame=", "manual reset frame=", "clean exit frame="]
    offset = 0
    for marker in markers:
        offset = text.index(marker,offset)+len(marker)
    if "FATAL" in text or " x=1 y=0 " not in text:
        raise ValueError("Completed guest log lacks right input or reports an error")
    jump = re.search(r"frame frame=\d+ x=19 y=(\d+) vx=0\.000 vy=(-[\d.]+) ground=\d dead=0 resets=0",text)
    death = re.search(r"death frame=\d+ x=(\d+) y=\d+ .* dead=1 resets=0",text)
    if not jump or int(jump[1]) >= 144 or not death or int(death[1]) <= 19:
        raise ValueError("Completed log does not prove jump/right movement/actual death")
    for marker in ("manual reset", "clean exit"):
        if not re.search(marker+r" frame=\d+ x=19 y=144 .* dead=0 resets=1",text):
            raise ValueError("Completed guest reset/exit state is not fresh")
    return markers


class XError(C.Structure):
    _fields_ = [("type",C.c_int),("display",C.c_void_p),("resource",C.c_ulong),("serial",C.c_ulong),
                ("code",C.c_ubyte),("request",C.c_ubyte),("minor",C.c_ubyte)]


class ClientMessage(C.Structure):
    _fields_ = [("type",C.c_int),("serial",C.c_ulong),("send_event",C.c_int),("display",C.c_void_p),
                ("window",C.c_ulong),("message_type",C.c_ulong),("format",C.c_int),("data",C.c_long*5)]


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
        while self.x.XPending(self.display):
            event = (C.c_long*24)()
            self.x.XNextEvent(self.display,event)

    def key(self, window, code, pressed):
        if not self.focused(window):
            raise RuntimeError("OUR window focus is unverified; refusing input")
        if not self.xt.XTestFakeKeyEvent(self.display,code,pressed,0):
            raise RuntimeError("XTest key event failed")
        if pressed:
            self.keys.add(code)
        else:
            self.keys.discard(code)
        self.x.XFlush(self.display)
        self.x.XSync(self.display,False)
        if any(error != 3 for error,request in self.errors):
            raise RuntimeError(f"X11 request failed: {self.errors}")
        deadline = time.monotonic()+3
        while True:
            keymap = (C.c_ubyte*32)()
            self.x.XQueryKeymap(self.display,keymap)
            if bool(keymap[code//8] & (1<<(code%8))) == pressed:
                return
            remaining = deadline-time.monotonic()
            if remaining <= 0 or not select.select([self.fd],[],[],remaining)[0]:
                raise RuntimeError("XTest did not establish the requested server key state within 3 seconds")
            self.drain()

    def close(self):
        for code in self.keys:
            self.xt.XTestFakeKeyEvent(self.display,code,False,0)
        self.x.XSync(self.display,False)
        self.x.XCloseDisplay(self.display)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vpk", type=Path, required=True)
    parser.add_argument("--existing", type=Path, default=Path("/home/fred/cloudpunk-vita/tools/vita3k"))
    args = parser.parse_args()
    state, output, existing = args.state.resolve(), args.output.resolve(), args.existing.resolve()
    if not output.is_relative_to(Path(".audit/native-room-vita").resolve()):
        parser.error("Evidence must remain beneath .audit/native-room-vita")
    output.mkdir(parents=True,exist_ok=True)
    fs, config = prepare(state,existing)
    if (fs / "ux0/app" / TITLE).exists():
        parser.error("Use a fresh isolated state; never overwrite an installed title")
    x = X11()
    inventory = x.windows()
    (output / "windows-before.json").write_text(json.dumps(inventory,indent=2)+"\n")
    if any(TITLE in window["name"] or "Celeste Native Room Diagnostic" in window["name"] for window in inventory):
        x.close()
        raise RuntimeError("Diagnostic window already exists; ownership ambiguous")
    libc = C.CDLL(None,use_errno=True)
    libc.inotify_init1.argtypes, libc.inotify_init1.restype = [C.c_int], C.c_int
    libc.inotify_add_watch.argtypes, libc.inotify_add_watch.restype = [C.c_int,C.c_char_p,C.c_uint32], C.c_int
    notify = libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
    if notify < 0 or libc.inotify_add_watch(notify,os.fsencode(fs / "ux0/data"),0x8|0x80) < 0:
        raise OSError(C.get_errno(),"inotify initialization failed")
    command, env = launch_command(state,existing,["-c",str(config.parent),"--keep-config","--",str(args.vpk.resolve())])
    events = []
    process = None
    process_fd = None
    ready = fs / "ux0/data/celeste_native_room.ready"
    last_ready = ""

    def wait(predicate, timeout=120):
        nonlocal last_ready
        deadline = time.monotonic()+timeout
        while True:
            if predicate():
                return
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Bounded X11/readiness wait expired")
            readable,_,_ = select.select([x.fd,notify,process_fd],[],[],remaining)
            if process_fd in readable:
                raise RuntimeError(f"Owned emulator exited before smoke completion: {process.wait()}")
            if x.fd in readable:
                x.drain()
            if notify in readable:
                os.read(notify,65536)
                if ready.exists():
                    value = ready.read_text()
                    if value != last_ready:
                        last_ready = value
                        events.append({"readiness_only":value.strip(),"at":time.monotonic()})

    def delay(seconds):
        deadline = time.monotonic()+seconds
        wait(lambda: time.monotonic() >= deadline,seconds+0.1)

    try:
        with zipfile.ZipFile(args.vpk) as package:
            installed = {name:package.read(name) for name in package.namelist()}
        provenance = json.loads(installed["assets/native-room/provenance.json"])
        revision = provenance["revision"] + ("-dirty" if provenance["tracked_changes"] else "")
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
        command, env = launch_command(state,existing,["-c",str(config.parent),"--keep-config","-r",TITLE])
        with (output / "host.log").open("wb") as host:
            process = subprocess.Popen(command,env=env,cwd=state,stdout=host,stderr=subprocess.STDOUT)
            process_fd = os.pidfd_open(process.pid)
            events.append({"runtime_pid":process.pid,"command":command})
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
            x.x.XSelectInput(x.display,wid,(1<<0)|(1<<1)|(1<<21)|(1<<22))
            x.activate(wid)
            wait(lambda: x.focused(wid),10)

            def change(code,pressed,expected="sampled"):
                before = last_ready
                x.key(wid,code,pressed)
                events.append({"injected_keycode":code,"pressed":pressed,"focus_and_server_key_state_verified":True})
                wait(lambda: last_ready != before and last_ready.startswith(expected+" "),30)

            change(53,True)
            delay(0.25)
            change(53,False)
            delay(1.0)
            change(114,True)
            wait(lambda: last_ready.startswith("dead "),60)
            change(114,False)
            change(55,True,"reset")
            change(55,False)
            x.key(wid,36,True)
            try:
                status = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.terminate()
                status = process.wait(timeout=15)
                events.append({"stopped_owned_host_after_guest_exit":True})
            events.append({"host_exit_code":status})
        guest = fs / "ux0/data/celeste_native_room.log"
        data = guest.read_bytes()
        (output / "guest.log").write_bytes(data)
        text = data.decode()
        markers = verify_guest(text,revision)
        events.append({"completed_guest_markers":markers,"claim":"Diagnostic only; not full game or hardware proof"})
    finally:
        x.close()
        os.close(notify)
        if process_fd is not None:
            os.close(process_fd)
        if process is not None and process.returncode is None:
            process.terminate()
            process.wait(timeout=15)
            events.append({"stopped_owned_host_on_failure":True})
        guest = fs / "ux0/data/celeste_native_room.log"
        if guest.is_file():
            (output / "guest.log").write_bytes(guest.read_bytes())
        (output / "events.json").write_text(json.dumps(events,indent=2)+"\n")


if __name__ == "__main__":
    main()
