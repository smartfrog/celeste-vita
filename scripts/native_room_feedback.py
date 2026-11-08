"""Durable stage feedback from our guest's closed native-renderer export."""

import hashlib
import json
from pathlib import Path
from convert_native_frame import ppm_to_png
from native_room_revision import REPO_ROOT

RENDER_STAGE = "after_draw_glFinish_GL_BACK_before_swap"


def save_feedback(path, feedback):
    path = Path(path).resolve()
    if not path.is_relative_to(REPO_ROOT / ".audit/native-room-vita"):
        raise ValueError("Feedback must remain under private diagnostic evidence")
    temporary = path.with_name(path.name+".new")
    temporary.write_text(json.dumps(feedback,indent=2)+"\n")
    temporary.replace(path)


def new_feedback(revision, vpk):
    return {"revision":revision,"vpk":{"path":str(vpk),"sha256":hashlib.sha256(vpk.read_bytes()).hexdigest() if vpk.is_file() else None},
            "stages":{"build":False,"package_verified":False,"startup":False,"native_image":False,
                      "image_openable":False,"input":False,"clean_exit":False,"full_completion":False},
            "artifacts":{},"errors":[],"visual_review":"pending_parent_not_claimed",
            "method":"OUR guest glReadPixels GL_BACK once; lossless P6-to-PNG conversion; no OS screen capture"}


def collect_native_frame(filesystem, output, revision):
    guest_path = f"ux0:data/celeste_native_room-{revision}.ppm"
    source = filesystem / "ux0/data" / guest_path.split(":data/",1)[1]
    receipt_path = Path(str(source)+".txt")
    if not source.is_file() or not receipt_path.is_file():
        return None
    if receipt_path.stat().st_size > 2048 or source.stat().st_size > 960*544*3+64:
        raise ValueError("Native export/receipt exceeds bound")
    receipt = receipt_path.read_text()
    if not receipt.startswith("frame_saved ") or not receipt.endswith("\n"):
        raise ValueError("Native export has no complete frame_saved receipt")
    metadata = dict(field.split("=",1) for field in receipt.split()[1:])
    expected = {"path":guest_path,"revision":revision,"width":"960","height":"544","stage":RENDER_STAGE,
                "frame":"0","format":"P6_RGB_top_down"}
    if any(metadata.get(key) != value for key,value in expected.items()):
        raise ValueError("Native export receipt does not match revision/path/stage/dimensions")
    ppm = source.read_bytes()
    if not ppm.startswith(b"P6\n960 544\n255\n"):
        raise ValueError("Native export dimensions are not the full framebuffer")
    png = ppm_to_png(ppm)
    artifacts = {}
    for name,data in (("native-frame.ppm",ppm),("native-frame.png",png),("native-frame.txt",receipt.encode())):
        destination = output / name
        with destination.open("xb") as stream:
            if stream.write(data) != len(data):
                raise OSError(f"Incomplete native artifact copy: {destination}")
        artifacts[name] = {"path":str(destination),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
    pixels = ppm.split(b"\n",3)[3]
    black_bars = pixels[:960*2*3] == bytes(960*2*3) and pixels[-960*2*3:] == bytes(960*2*3)
    return {"guest_path":guest_path,"original_guest_file":str(source),"receipt":str(receipt_path),"revision":revision,
            "render_stage":RENDER_STAGE,"dimensions":[960,544],
            "frame_state":{key:float(metadata[key]) for key in ("frame","x","y","vx","vy","ground","dead","resets")},
            "black_letterbox_rows":black_bars,"nonzero_rgb_bytes":sum(value != 0 for value in pixels),"artifacts":artifacts}
