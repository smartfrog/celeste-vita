import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from compare_decal_draws import compare, recompute_quad
from prepare_decals import PAGE_HEIGHT, PAGE_WIDTH, protocol_text


BANNERS = [("B", 20, "1-forsakencity/ragsB"), ("B", 21, "1-forsakencity/rags"),
           ("B", 22, "1-forsakencity/ragsB"), ("B", 23, "1-forsakencity/rags"),
           ("B", 24, "1-forsakencity/ragsB"), ("F", 2, "generic/grass_a"), ("F", 3, "generic/grass_d")]


def make_fixture():
    page = bytearray(PAGE_WIDTH * PAGE_HEIGHT * 4)
    textures = {}
    for index in range(15):
        u, v, width, height = 1 + (index % 5) * 10, 1 + (index // 5) * 10, 4, 4
        for dy in range(height):
            for dx in range(width):
                offset = ((v + dy) * PAGE_WIDTH + u + dx) * 4
                page[offset:offset + 4] = bytes((index + 1, dx, dy, 255))
        name = f"decals/generic/t{index:02d}"
        textures[name] = {"name": name, "u": u, "v": v, "width": width, "height": height,
                          "draw_offset": [1, 1], "frame": [8, 8]}
    instances = []
    for index in range(20):
        instances.append({"group": "bgdecals", "source_index": index, "position": [index * 2, index * 3],
                          "scale": [1, 1], "name": f"decals/generic/t{index % 15:02d}",
                          "depth": 9000, "frame": [8, 8], "draw_offset": [1, 1], "origin": [3, 3]})
    for index in range(2):
        instances.append({"group": "fgdecals", "source_index": index, "position": [100 + index, 50],
                          "scale": [1, -1] if index == 0 else [-1, 1], "name": f"decals/generic/t{index:02d}",
                          "depth": -10500, "frame": [8, 8], "draw_offset": [1, 1], "origin": [3, 3]})
    draws = []
    for instance in instances:
        texture = {**textures[instance["name"]], "page": [PAGE_WIDTH, PAGE_HEIGHT]}
        quad = recompute_quad(instance, texture)
        points = [(quad["left"], quad["top"]), (quad["right"], quad["top"]),
                  (quad["left"], quad["bottom"]), (quad["right"], quad["bottom"])]
        import struct
        draw = {k: instance[k] for k in ("group", "source_index", "name", "position", "scale", "depth",
                                         "frame", "draw_offset", "origin")}
        draw.update({"behavior": "DecalImage",
                     "vertices_bits": [struct.pack(">f", value).hex() for point in points for value in point]})
        draws.append(draw)
    oracle = {"oracle": {"static_profile": {"draws": draws},
                         "banner_exclusion": {"attempts": [
                             {"group": "bgdecals" if layer == "B" else "fgdecals", "source_index": index,
                              "name": "decals/" + name} for layer, index, name in BANNERS]}}}
    return bytes(page), textures, instances, draws, oracle


class ComparatorSerializedBindingTests(unittest.TestCase):
    def fixture(self):
        page, textures, instances, draws, oracle = make_fixture()
        temporary = tempfile.TemporaryDirectory()
        prepared = Path(temporary.name)
        banners = BANNERS
        protocol = protocol_text(textures, instances, banners, page)
        (prepared / "decal0.rgba").write_bytes(page)
        (prepared / "decals.txt").write_bytes(protocol)
        texture_metadata = {}
        for name, texture in textures.items():
            rows = []
            for dy in range(texture["height"]):
                start = ((texture["v"] + dy) * PAGE_WIDTH + texture["u"]) * 4
                rows.append(page[start:start + texture["width"] * 4])
            texture_metadata[name] = {**texture, "crop_sha256": hashlib.sha256(b"".join(rows)).hexdigest()}
        provenance = {"files": {"decal0.rgba": hashlib.sha256(page).hexdigest(),
                                "decals.txt": hashlib.sha256(protocol).hexdigest()},
                      "page": {"width": PAGE_WIDTH, "height": PAGE_HEIGHT, "bytes": len(page),
                               "sha256": hashlib.sha256(page).hexdigest()},
                      "classification": {"static": 22, "bg": 20, "fg": 2, "banner_omitted": 7, "banner_ids": BANNERS},
                      "instances": instances, "textures": texture_metadata}
        (prepared / "provenance.json").write_text(json.dumps(provenance))
        return temporary, prepared, provenance, oracle

    def refresh_protocol_hash(self, prepared, provenance):
        provenance["files"]["decals.txt"] = hashlib.sha256((prepared / "decals.txt").read_bytes()).hexdigest()
        (prepared / "provenance.json").write_text(json.dumps(provenance))

    def mutate_instance(self, prepared, provenance, source_index, token, value):
        lines = (prepared / "decals.txt").read_text().splitlines()
        for index, line in enumerate(lines):
            if line.startswith(f"B {source_index} "):
                fields = line.split()
                fields[token] = str(value)
                lines[index] = " ".join(fields)
                break
        (prepared / "decals.txt").write_text("\n".join(lines) + "\n")
        self.refresh_protocol_hash(prepared, provenance)

    def test_baseline_serialized_csd1_matches_all_source_draws(self):
        temporary, prepared, provenance, oracle = self.fixture()
        with temporary:
            result = compare(oracle, prepared)
            self.assertEqual(result["static"], 22)
            self.assertEqual(result["banner_omitted"], 7)

    def test_refreshed_hash_position_mutation_is_rejected(self):
        temporary, prepared, provenance, oracle = self.fixture()
        with temporary:
            self.mutate_instance(prepared, provenance, 0, 2, 257)
            with self.assertRaises(ValueError):
                compare(oracle, prepared)

    def test_refreshed_hash_scale_mutation_is_rejected(self):
        temporary, prepared, provenance, oracle = self.fixture()
        with temporary:
            self.mutate_instance(prepared, provenance, 0, 4, -1)
            with self.assertRaises(ValueError):
                compare(oracle, prepared)

    def test_refreshed_hash_texture_uv_mutation_is_rejected(self):
        temporary, prepared, provenance, oracle = self.fixture()
        with temporary:
            lines = (prepared / "decals.txt").read_text().splitlines()
            for index, line in enumerate(lines):
                if line.startswith("decals/generic/t00 "):
                    fields = line.split()
                    fields[1] = str(int(fields[1]) + 1)
                    lines[index] = " ".join(fields)
                    break
            (prepared / "decals.txt").write_text("\n".join(lines) + "\n")
            self.refresh_protocol_hash(prepared, provenance)
            with self.assertRaises(ValueError):
                compare(oracle, prepared)

    def test_refreshed_hash_instance_order_mutation_is_rejected(self):
        temporary, prepared, provenance, oracle = self.fixture()
        with temporary:
            lines = (prepared / "decals.txt").read_text().splitlines()
            first = next(i for i, line in enumerate(lines) if line.startswith("B 0 "))
            second = next(i for i, line in enumerate(lines) if line.startswith("B 1 "))
            lines[first], lines[second] = lines[second], lines[first]
            (prepared / "decals.txt").write_text("\n".join(lines) + "\n")
            self.refresh_protocol_hash(prepared, provenance)
            with self.assertRaises(ValueError):
                compare(oracle, prepared)

    def test_refreshed_hash_omission_class_mutation_is_rejected(self):
        temporary, prepared, provenance, oracle = self.fixture()
        with temporary:
            lines = (prepared / "decals.txt").read_text().splitlines()
            index = lines.index("F 2 generic/grass_a")
            lines[index] = "B 20 1-forsakencity/ragsB"
            (prepared / "decals.txt").write_text("\n".join(lines) + "\n")
            self.refresh_protocol_hash(prepared, provenance)
            with self.assertRaises(ValueError):
                compare(oracle, prepared)

    def test_provenance_only_instance_mutation_does_not_override_serialized_source(self):
        temporary, prepared, provenance, oracle = self.fixture()
        with temporary:
            provenance["instances"][0]["position"] = [999, 999]
            (prepared / "provenance.json").write_text(json.dumps(provenance))
            result = compare(oracle, prepared)
            self.assertEqual(result["static"], 22)


if __name__ == "__main__":
    unittest.main()
