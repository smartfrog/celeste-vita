"""Read-only global CPU gameplay comparison against independently bound SOURCE owners."""

import argparse
from collections import Counter
from itertools import zip_longest
import json
from pathlib import Path
import struct

from compare_native_player_draw import SOURCE_IDENTITY
from native_room_revision import file_identity
from prepare_native_transition_fixture import room_records
from prepare_static_decal_descriptors import atlas_key

ROOMS_IDENTITY = {"bytes": 15518, "sha256": "b5c5814db9cb0084099a552d38890887f9f9602a97d86d99f07969e79602809f"}
IMAGE_FIELDS = ("sheet", "dimensions", "sourceRectangle", "clipping", "color", "effects", "finiteGeometry")
FLOAT_FIELDS = ("position", "origin", "scale", "rotation")
GLOBAL_KINDS = {"Player", "BackgroundTiles", "SolidTiles", "TotalStrawberriesDisplay"}
OBJECT_KINDS = {"spike_up": "Spikes", "spike_left": "Spikes", "jump_thru": "JumpthruPlatform",
                "strawberry": "Strawberry", "spring": "Spring"}


def require(value, message):
    if not value:
        raise ValueError(message)


def float_words(value):
    if isinstance(value, list):
        return [float_words(item) for item in value]
    return struct.pack("<f", value)


def geometry_shape(command):
    vertices = command["verticesFloat32Bits"]
    require(isinstance(vertices, list) and vertices, "Missing geometry vertices")
    for vertex in vertices:
        require(isinstance(vertex, list) and vertex and all(type(word) is int and -2147483648 <= word <= 2147483647 for word in vertex),
                "Geometry must retain signed IEEE float32 words")
    return tuple(map(len, vertices))


def compare_frame(source, native):
    tick = source["tick"]
    require(tick == native["tick"], "Global frame order differs")
    expected, actual = source["commands"], native["commands"]
    require(len(expected) == len(actual), f"tick {tick}: global command count differs")
    require(len(source["dispatch"]) == len(native["dispatch"]), f"tick {tick}: dispatch range count differs")
    require([source["keys"][identity] for identity in source["excluded"]] ==
            [native["keys"][identity] for identity in native["excluded"]], f"tick {tick}: HUD exclusion differs")
    cursor, words, nonfinite = 0, 0, 0
    shapes, owners, components = Counter(), Counter(), Counter()
    for dispatch, (wanted_range, actual_range) in enumerate(zip(source["dispatch"], native["dispatch"])):
        key = source["keys"][wanted_range["entity"]]
        require(key == native["keys"][actual_range["ownerIdentity"]], f"tick {tick}: dispatch {dispatch} semantic owner differs")
        begin, end = wanted_range["drawStart"], wanted_range["drawEnd"]
        require(begin == cursor and begin <= end <= len(expected) and (actual_range["begin"], actual_range["end"]) == (begin, end),
                f"tick {tick}: dispatch {dispatch} range differs or does not partition global commands")
        reason = actual_range["emptyReason"]
        if begin == end:
            policy = {"Entity": "scene-helper-no-capture-calls", "WindController": "wind-no-capture-calls",
                      "ParticleSystem": "particle-system-no-active-images"}.get(key[0])
            require((policy is not None and reason == policy) or (key[0] in ("BackgroundTiles", "SolidTiles") and reason is None),
                    f"tick {tick}: dispatch {dispatch} unexplained empty producer")
        else:
            require(reason is None, f"tick {tick}: nonempty producer marked empty")
        for index in range(begin, end):
            wanted, command = expected[index], actual[index]
            context = f"tick {tick} global {index} owner {key} piece {index-begin}"
            require(wanted["index"] == command["index"] == index and wanted["owner"]["entity"] == wanted_range["entity"] and
                    command["ownerIdentity"] == actual_range["ownerIdentity"] and command["dispatchIndex"] == dispatch and
                    command["piece"] == index-begin, context + ": command/range/component-piece binding differs")
            require(wanted["owner"]["componentType"] == command["componentType"], context + ": componentType differs")
            for field in IMAGE_FIELDS:
                require(wanted[field] == command[field], context + ": " + field + " differs")
            for field in FLOAT_FIELDS:
                require(float_words(wanted[field]) == float_words(command[field]), context + ": " + field + " float32 differs")
            shape = geometry_shape(wanted)
            require(shape == geometry_shape(command), context + ": geometry shape differs")
            for vertex, (source_words, native_words) in enumerate(zip(wanted["verticesFloat32Bits"], command["verticesFloat32Bits"])):
                for field, (source_word, native_word) in enumerate(zip(source_words, native_words)):
                    require(source_word == native_word, context + f": geometry vertex {vertex} field {field}: SOURCE {source_word} native {native_word}")
            words += sum(shape)
            shapes[str(shape)] += 1
            owners[key[0]] += 1
            components[f"{key[0]}/{command['componentType']}"] += 1
            nonfinite += not command["finiteGeometry"]
        cursor = end
    require(cursor == len(expected), f"tick {tick}: leftover commands outside dispatch ranges")
    require(native["summary"] == {"commands": cursor, "geometryWords": words, "renderCalls": 1}, f"tick {tick}: global summary differs")
    return {"commands": cursor, "words": words, "nonfinite": nonfinite, "shapes": shapes, "owners": owners, "components": components}


class SourceBindings:
    def __init__(self, authored):
        self.objects, self.decals, self.identities, self.reverse = {}, {}, {}, {}
        for room in room_records(authored):
            for kind, identity, x, y, _size in room["objects"]:
                key = (room["name"], OBJECT_KINDS[kind], (x, y))
                require(key not in self.objects, "Ambiguous authored entity position")
                self.objects[key] = identity
        for raw_room in authored:
            attributes = raw_room["attributes"]
            room = attributes["name"][4:]
            for group in raw_room["children"]:
                if group["name"] not in ("bgdecals", "fgdecals"):
                    continue
                background = group["name"] == "bgdecals"
                for ordinal, decal in enumerate(group["children"]):
                    data = decal["attributes"]
                    key = (room, background, atlas_key(data["texture"]), (attributes["x"]+data["x"], attributes["y"]+data["y"]))
                    require(key not in self.decals, "Ambiguous authored decal identity")
                    self.decals[key] = ordinal

    def bind(self, state, roster):
        transition = state.get("transition")
        iterator = transition.get("iterator") if transition else None
        outgoing = set(iterator.get("outgoing") or []) if iterator else set()
        keys = {}
        for owner in roster:
            identity, kind = owner["entity"], owner["type"]
            room = "1" if identity in outgoing else state["room"]
            if kind in GLOBAL_KINDS:
                key = (kind,)
            elif kind == "ParticleSystem":
                require(owner["depth"] in (8000, -8000, -50000), "Unknown SOURCE particle role")
                key = (kind, owner["depth"])
            elif kind == "Decal":
                authored = (room, owner["depth"] > 0, owner["decal"]["Name"], tuple(owner["position"]))
                require(authored in self.decals, "SOURCE decal lacks independently pinned authored binding")
                key = (kind, room, owner["depth"] > 0, self.decals[authored])
            elif kind in OBJECT_KINDS.values():
                authored = (room, kind, tuple(owner["position"]))
                require(authored in self.objects, "SOURCE entity lacks independently pinned authored binding")
                key = (kind, room, self.objects[authored])
            elif kind in ("Entity", "WindController"):
                key = (kind, room)
            else:
                raise ValueError("Unknown SOURCE gameplay owner family: " + kind)
            require(identity not in keys and key not in keys.values(), "Duplicate SOURCE semantic owner")
            require(self.identities.setdefault(identity, key) == key and self.reverse.setdefault(key, identity) == identity,
                    "SOURCE persistent/lifetime binding changed")
            keys[identity] = key
        return keys


def source_frames(path, bindings):
    state, roster, commands, tick = None, None, [], None
    with path.open() as stream:
        for line in stream:
            if not line.startswith(('{"event":"draw-state"', '{"event":"draw-roster"', '{"event":"draw-command"', '{"event":"draw-dispatch"')):
                continue
            row = json.loads(line)
            if row["event"] == "draw-state" and row["phase"] == "before-draw":
                require(state is None, "Duplicate SOURCE frame")
                state, tick = row["state"], row["tick"]
            elif row["event"] == "draw-roster":
                require(state is not None and roster is None and row["tick"] == tick, "Unbound SOURCE roster")
                roster = row["live"]
            elif row["event"] == "draw-command":
                require(state is not None and row["tick"] == tick, "Unbound SOURCE command")
                commands.append(row)
            elif row["event"] == "draw-dispatch":
                require(state is not None and roster is not None and row["tick"] == tick and row["commands"] == len(commands), "Unbound SOURCE dispatch")
                require([owner["entity"] for owner in roster if owner["Visible"] and not owner["hudExcluded"]] ==
                        [owner["entity"] for owner in row["entities"]], "SOURCE dispatch differs from actual captured roster")
                batches = row["batches"]
                require(len(batches) == 1 and batches[0]["SortMode"] == "Deferred" and not batches[0]["HasEffect"] and
                        (batches[0]["DrawStart"], batches[0]["DrawEnd"]) == (0, len(commands)), "SOURCE capture batch contract changed")
                entities = {entity["id"]: entity for entity in state["entities"]}
                for command in commands:
                    owner = command["owner"]
                    require(owner["entity"] in entities and owner["type"] == entities[owner["entity"]]["type"], "SOURCE command owner attribution changed")
                    if owner["componentType"] is not None:
                        require(any(component["id"] == owner["component"] and component["type"] == owner["componentType"]
                                    for component in entities[owner["entity"]]["components"]), "SOURCE component not owned by captured entity")
                yield {"tick": tick, "commands": commands, "dispatch": row["entities"], "keys": bindings.bind(state, roster),
                       "excluded": [owner["entity"] for owner in roster if owner["hudExcluded"]]}
                state, roster, commands, tick = None, None, [], None
    require(state is None and not commands, "Truncated SOURCE draw capture")


def native_key(owner):
    kind = owner["kind"]
    if kind in GLOBAL_KINDS:
        return (kind,)
    if kind == "ParticleSystem":
        return (kind, owner["sortDepthBand"])
    if kind == "Decal":
        return (kind, owner["room"], owner["sortDepthBand"] > 0, owner["authoredId"])
    if kind in ("Entity", "WindController"):
        return (kind, owner["room"])
    require(kind in OBJECT_KINDS.values(), "Unknown native gameplay owner family")
    return (kind, owner["room"], owner["authoredId"])


def native_frames(path):
    roster, dispatch, ranges, commands, identities, reverse = None, None, None, [], {}, {}
    ended = False
    with path.open() as stream:
        for line in stream:
            if not line.startswith(('{"event":"draw-owner-', '{"event":"gameplay-', '{"event":"native-ended"')):
                continue
            row = json.loads(line)
            require(not ended, "Native events after route end")
            event = row["event"]
            if event == "draw-owner-roster":
                require(roster is None, "Duplicate native roster")
                roster = row
            elif event == "draw-owner-dispatch":
                require(dispatch is None, "Duplicate native dispatch")
                dispatch = row
            elif event == "gameplay-dispatch":
                require(ranges is None, "Duplicate global native ranges")
                ranges = row
            elif event == "gameplay-command":
                commands.append(row)
            elif event == "gameplay-frame":
                require(roster is not None and dispatch is not None and ranges is not None and
                        row["tick"] == roster["tick"] == dispatch["tick"] == ranges["tick"] and all(command["tick"] == row["tick"] for command in commands),
                        "Missing or unbound global native frame")
                keys = {owner["identity"]: native_key(owner) for owner in roster["live"]}
                require(len(keys) == len(roster["live"]) == len(set(keys.values())), "Duplicate native semantic owner")
                for identity, key in keys.items():
                    require(identities.setdefault(identity, key) == key and reverse.setdefault(key, identity) == identity, "Native lifetime binding changed")
                require([span["ownerIdentity"] for span in ranges["ranges"]] == dispatch["order"] and
                        len(set(dispatch["order"])) == len(dispatch["order"]), "Global native ranges do not follow actual projection dispatch")
                by_identity = {owner["identity"]: owner for owner in roster["live"]}
                require(set(dispatch["order"]) == {owner["identity"] for owner in roster["live"] if owner["visible"] and not owner["hudExcluded"]},
                        "Native live owner lacks unique dispatch membership")
                for span in ranges["ranges"]:
                    owner = by_identity[span["ownerIdentity"]]
                    require((span["kind"], span["room"], span["authoredId"], span["background"]) ==
                            (owner["kind"], owner["room"], owner["authoredId"], owner["kind"] == "Decal" and owner["sortDepthBand"] > 0),
                            "Global native range semantic metadata differs from actual roster binding")
                excluded = [owner["identity"] for owner in roster["live"] if owner["hudExcluded"]]
                require(ranges["excluded"] == [{"ownerIdentity": identity, "reason": "hud-outside-gameplay-capture"} for identity in excluded], "Missing explicit native HUD policy")
                yield {"tick": row["tick"], "commands": commands, "keys": keys, "dispatch": ranges["ranges"], "excluded": excluded,
                       "summary": {key: row[key] for key in ("commands", "geometryWords", "renderCalls")}}
                roster, dispatch, ranges, commands = None, None, None, []
            elif event == "native-ended":
                require(row["frames"] == 514 and row["loads"] == 2 and row["reloads"] == 0, "Native route ended incorrectly")
                ended = True
    require(ended and roster is None and dispatch is None and ranges is None and not commands, "Incomplete global native trace")


def compare(source, native, rooms):
    require(file_identity(source) == SOURCE_IDENTITY, "Frozen SOURCE draw trace changed")
    require(file_identity(rooms) == ROOMS_IDENTITY, "Pinned authored room metadata changed")
    bindings = SourceBindings(json.loads(rooms.read_text()))
    counts, shapes, owners, components = Counter(), Counter(), Counter(), Counter()
    boundaries = {}
    for tick, pair in enumerate(zip_longest(source_frames(source, bindings), native_frames(native))):
        wanted, actual = pair
        require(wanted is not None and actual is not None and wanted["tick"] == actual["tick"] == tick, "Global route coverage differs")
        result = compare_frame(wanted, actual)
        counts.update({key: result[key] for key in ("commands", "words", "nonfinite")})
        shapes.update(result["shapes"]);owners.update(result["owners"]);components.update(result["components"])
        if tick in (35, 374, 412, 413):
            boundaries[tick] = {"commands": result["commands"], "dispatch_semantics": [wanted["keys"][span["entity"]] for span in wanted["dispatch"]]}
        counts["frames"] += 1
    require(counts["frames"] == 514 and counts["commands"] == 680226, "Frozen global route total changed")
    return {**counts, "geometry_shapes": shapes, "by_owner": owners, "by_component": components,
            "semantic_owners": len(bindings.reverse), "dispatch_boundaries": boundaries, "mismatches": 0,
            "scope": "GameplayRenderer CPU logical descriptors and captured pre-batch XYZUV bits; no overload identity, GPU, assets, Level hooks or full-game claim"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--rooms", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(compare(arguments.source, arguments.native, arguments.rooms), indent=2))
