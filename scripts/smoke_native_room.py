#!/usr/bin/env python3
"""Bounded X11 smoke for OUR isolated Vita3K title; never drive another window."""

import argparse
import ctypes as C
import json
import os
from pathlib import Path
import select
import subprocess
import time

from vita_room_emulator import TITLE, prepare, launch_command


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
        }
        for name, (result, arguments) in signatures.items():
            f = getattr(self.x,name)
            f.restype, f.argtypes = result, arguments
        self.xt.XTestFakeKeyEvent.argtypes = [C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
        self.xt.XTestFakeKeyEvent.restype = C.c_int
        self.display = self.x.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError("Cannot open the existing X11 display")
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
        with (output / "host.log").open("wb") as host:
            process = subprocess.Popen(command,env=env,cwd=state,stdout=host,stderr=subprocess.STDOUT)
            process_fd = os.pidfd_open(process.pid)
            window = None

            def find_window():
                nonlocal window
                matches = [w for w in x.windows() if TITLE in w["name"] and "OpenGL" in w["name"]]
                if len(matches) > 1:
                    raise RuntimeError("Ambiguous diagnostic game windows")
                if not matches:
                    return False
                window = matches[0]
                if not window["pid"] or str(config.parent).encode() not in Path(f'/proc/{window["pid"][0]}/cmdline').read_bytes():
                    raise RuntimeError("Diagnostic window PID does not own isolated config")
                return True

            wait(find_window)
            events.append({"game_window":window})
            wid = window["id"]
            wait(lambda: last_ready.startswith("ready "))
            x.x.XRaiseWindow(x.display,wid)
            x.x.XSetInputFocus(x.display,wid,2,0)
            x.x.XFlush(x.display)
            wait(lambda: x.focused(wid),10)
            subprocess.run(["import","-window",str(wid),str(output / "room.png")],check=True,timeout=30)

            def change(code,pressed,expected="sampled"):
                before = last_ready
                x.key(wid,code,pressed)
                wait(lambda: last_ready != before and last_ready.startswith(expected+" "),30)

            change(53,True)
            delay(0.25)
            change(53,False)
            delay(1.0)
            change(114,True)
            wait(lambda: last_ready.startswith("dead "),60)
            subprocess.run(["import","-window",str(wid),str(output / "death.png")],check=True,timeout=30)
            change(114,False)
            change(55,True,"reset")
            change(55,False)
            subprocess.run(["import","-window",str(wid),str(output / "reset.png")],check=True,timeout=30)
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
        markers = ["DIAGNOSTIC boot", "assets ready", "frame ready", "cross_held=1 cross_pressed=1", "death frame=", "manual reset frame=", "clean exit frame="]
        offset = 0
        for marker in markers:
            offset = text.index(marker,offset)+len(marker)
        if "FATAL" in text or "dead=1 resets=0" not in text or "dead=0 resets=1" not in text:
            raise RuntimeError("Completed guest log fails lifecycle checks")
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
        (output / "events.json").write_text(json.dumps(events,indent=2)+"\n")


if __name__ == "__main__":
    main()
