"""Durable stage feedback from our guest's closed native-renderer export."""

import hashlib
import json
import math
from pathlib import Path
from convert_native_frame import ppm_to_png
from native_room_revision import REPO_ROOT

RENDER_STAGE = "after_draw_glFinish_GL_BACK_RGBA_CPU_before_swap"


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
                      "image_openable":False,"render_content":False,"input":False,"clean_exit":False,"full_completion":False},
            "artifacts":{},"errors":[],"visual_review":"pending_parent_not_claimed",
            "method":"OUR guest glReadPixels GL_BACK once; lossless P6-to-PNG conversion; no OS screen capture"}


def validate_textured_pixels(pixels, metadata, visuals, capture):
    expected = {"render_style":"textured_partial", "camera":"0,0", "body_draws":"1", "diagnostic_spike_markers":"5",
                "submitted_rgba_bytes":"164864", "alpha":"premultiplied_ONE_ONE_MINUS_SRC_ALPHA", "body_pose":"idle00_static_no_animation",
                "bg_draws":str(visuals["draw_counts"]["B"]), "fg_draws":str(visuals["draw_counts"]["F"])}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("Textured native receipt lacks exact style/camera/layers/bytes/alpha scope")
    colors = len({pixels[i:i+3] for i in range(0,len(pixels),3)})
    if colors < 16:
        raise ValueError("Textured frame lacks texture color diversity; debug palette is not textured proof")
    probes = []
    for probe in visuals["spawn_content_probes"]:
        if capture != "spawn" and probe["texture"] == 5:
            continue
        x, y = probe["screen_pixel"]
        actual = list(pixels[(y*960+x)*3:(y*960+x+1)*3])
        if actual != probe["expected_rgb"]:
            raise ValueError(f"Native source texture content/orientation probe failed for texture {probe['texture']}: {actual} != {probe['expected_rgb']}")
        probes.append({**probe,"actual_rgb":actual})
    return {"unique_rgb_colors":colors,"opaque_source_probes":probes,"partial_alpha_room_probe":visuals["alpha_probe"],
            "partial_alpha_claim":"Requested six crops contain only alpha 0/255; separate GPU blend diagnostic required" if visuals["alpha_probe"] is None else "source edge present"}


def collect_native_frame(filesystem, output, revision, capture="spawn", visual_provenance=None):
    if capture not in {"spawn", "wall_jump", "climb"}:
        raise ValueError("Unsupported explicit native capture policy")
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
                "format":"P6_RGB_top_down"}
    if capture == "spawn":
        expected["frame"] = "0"
    else:
        expected.update(capture=capture, state="1" if capture == "climb" else "0", dead="0", resets="0")
        if capture == "wall_jump":
            expected["jump_kind"] = "WallJump"
        else:
            expected.update(ground="0", grab="1")
        frame = metadata.get("frame", "")
        if not frame.isascii() or not frame.isdecimal() or str(int(frame)) != frame or int(frame) <= 0:
            raise ValueError("Deferred export must record an actual positive frame")
    if any(metadata.get(key) != value for key,value in expected.items()):
        raise ValueError("Native export receipt does not match revision/path/stage/dimensions")
    frame_state = {key:float(metadata[key]) for key in ("frame","x","y","vx","vy","ground","dead","resets")}
    if not all(math.isfinite(value) for value in frame_state.values()):
        raise ValueError("Nonfinite native frame state")
    if "state" in metadata:
        frame_state["state"] = int(metadata["state"])
    if capture == "climb":
        frame_state["stamina"] = float(metadata["stamina"])
        frame_state["grab"] = int(metadata["grab"])
        if not math.isfinite(frame_state["stamina"]) or not 0 < frame_state["stamina"] < 110:
            raise ValueError("Climb export must be airborne, held and actually drained")
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
    textured = validate_textured_pixels(pixels,metadata,visual_provenance,capture) if visual_provenance is not None else None
    if visual_provenance is None and metadata.get("render_style","debug") != "debug":
        raise ValueError("Textured export requires its exact staged visual provenance, not debug intent")
    return {"guest_path":guest_path,"original_guest_file":str(source),"receipt":str(receipt_path),"revision":revision,
            "render_stage":RENDER_STAGE,"dimensions":[960,544],
            "frame_state":frame_state,"jump_kind":metadata.get("jump_kind","None"),"capture":capture,
            "black_letterbox_rows":black_bars,"nonzero_rgb_bytes":sum(value != 0 for value in pixels),"artifacts":artifacts,
            "render_style":metadata.get("render_style","debug"),"camera":metadata.get("camera","0,0"),"textured_content":textured}
