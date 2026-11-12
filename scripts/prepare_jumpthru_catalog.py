"""Generate one private bounded JumpThru material from pinned atlas metadata and cached SOURCE."""
import argparse
import hashlib
import json
from pathlib import Path

from native_room_textures import atlas_metadata
from prepare_static_decal_descriptors import fnv1a, require

AUDIT = Path("/home/fred/projects/celeste-vita/.audit/native-jumpthru-command-projection-01")
PINS = {
    "platform": "256d58907b477c9c7f42bbcd5813fe7486f0881b91d504a622cf2f5582c4019e",
    "mtexture": "45847f23970911b07541e4bc367cbd156f3b4b1846b63b33d3fed9c7b65ebf6b",
    "image": "aa87a22589821fc3781672126e68f2195fb46348f261013d8a01c070b53821d3",
    "meta": "1f23b1f35544a3751ffec170b0230c7c9513000ab1549f78ebb9cb9f4203c8d9",
    "atlas": "b75f913d315bd641c35a4990d9041b238c0d9ef3f8b1247ec557de8a9defc1cc",
}
KEY = "objects/jumpthru/wood"


def encode(inputs):
    require(set(inputs) == set(PINS), "Missing JumpThru input pins")
    for name, expected in PINS.items():
        require(hashlib.sha256(inputs[name]).hexdigest() == expected, "JumpThru input pin changed: " + name)
    atlas = json.loads(inputs["atlas"])
    metadata = atlas_metadata(inputs["meta"])
    require(KEY in atlas and KEY in metadata and tuple(atlas[KEY]) == metadata[KEY],
            "JumpThru atlas metadata binding changed")
    require([key for key in atlas if key.startswith(KEY)] == [KEY], "JumpThru material is not a singleton")
    frame = metadata[KEY]
    sheet, x, y, width, height, ox, oy, fw, fh = frame
    require(sheet == "Gameplay0" and width == fw == 24 and fh == 16 and 8 < height <= 16 and ox == oy == 0,
            "Unsupported bounded JumpThru frame/trim")
    return ("\n".join(["CJTC1", *PINS.values(), " ".join(map(str, frame)) + " " + KEY]) + "\n").encode()


def prepare(paths, output):
    require(output.resolve().is_relative_to(AUDIT) and not output.exists(), "JumpThru output must be private and fresh")
    receipt_path = output.parent / "receipt.json"
    require(not receipt_path.exists(), "JumpThru receipt must be fresh")
    inputs = {name: path.read_bytes() for name, path in paths.items()}
    data = encode(inputs)
    receipt = {"schema": 1, "kind": "bounded-jumpthru-material", "materials": 1,
               "inputs": {name: {"path": str(paths[name]), "bytes": len(value), "sha256": PINS[name]}
                          for name, value in inputs.items()},
               "output": {"path": str(output), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                          "fnv1a": f"{fnv1a(data):08x}"}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(data)
    with receipt_path.open("x") as stream:
        json.dump(receipt, stream, indent=2)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in PINS:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare({name: getattr(args, name) for name in PINS}, args.output), indent=2))
