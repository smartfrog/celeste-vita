"""Native GameplayRenderer draw-owner projection vs accepted SOURCE: semantic owner differential.

Owners are bound by verified semantic identities (room, layer, authored ordinal/authored id),
not kind lists: the paired chronology and identity uniqueness are compared for every route tick.
The frozen accepted SOURCE trace is a TEST oracle only, streamed in place; production never
loads it. Scope: owner kind/order/visibility/HUD exclusion and outgoing retention; no draw
commands, span indexes or vertex parity are claimed.
"""
import copy
import hashlib
import json
import subprocess
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_TRACE = Path("/home/fred/projects/celeste-vita-worktrees/native-room-transition-vita"
                    "/.audit/native-room-transition-vita/gameplay-draw-profile-01"
                    "/clean-commit-a2af9d05b662/source-run-a/trace.jsonl")
SOURCE_IDENTITY = {"bytes": 575248334, "sha256": "8af9703eff54511307b57170bd7bbc98fb8efcd58eb5d7e9ef2e0972ab378073"}
NATIVE_NAME = Path(".audit/native-gameplay-draw-ownership-01/corrective-02/native-run/native-draw-8arg.jsonl")
NATIVE_IDENTITY = {"bytes": 11771390, "sha256": "eb38820aec8e6964b82c3ade71b618f030932576d74757533ec623578740502f"}
DIFFERENTIAL_TICKS = (0, 375)
INTRO_LAG_TICKS = (35, 36)
FOCUSED_POST_UNLOAD_TICKS = (413, 513)
FRAMES = 514
ANNOUNCED_COMMANDS = {
    0: {"BackgroundTiles": 688, "Decal": 98, "Spikes": 19, "SolidTiles": 478, "Player": 40},
    375: {"BackgroundTiles": 690, "Decal": 165, "Player": 22, "Spikes": 28, "JumpthruPlatform": 5,
          "Strawberry": 1, "ParticleSystem": 4, "Spring": 9, "SolidTiles": 480},
}
OUTGOING_WINDOW = range(374, 413)
ROOM_OBJECTS = {"1": {"Spikes": [7, 8, 9, 10, 11]},
                "2": {"JumpthruPlatform": [7], "Spikes": [8, 9, 14], "Strawberry": [11], "Spring": [12]}}
DECAL_BANDS = {"1": (25, 4), "2": (18, 5)}
PARTICLE_DEPTHS = (8000, -8000, -50000)


def file_identity(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def canonical_root():
    git_dir = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    return Path(git_dir).parent


def sample_source(path):
    ticks = {}
    current = None
    state_types = {}
    state_entities = {}
    outgoing_ids = set()
    room = None
    commands = Counter()
    with path.open() as stream:
        for line in stream:
            if line.startswith('{"event":"draw-command"'):
                if current in DIFFERENTIAL_TICKS:
                    commands[json.loads(line)["owner"]["type"]] += 1
                continue
            if not line.startswith('{"event":"draw-'):
                continue
            row = json.loads(line)
            event = row["event"]
            if event == "draw-state":
                current = row["tick"]
                if row["phase"] != "before-draw":
                    continue
                state = row["state"]
                room = state["room"]
                state_entities = {value["id"]: value for value in state["entities"]}
                state_types = {key: value["type"] for key, value in state_entities.items()}
                transition = state.get("transition")
                iterator = transition.get("iterator") if transition else None
                outgoing = iterator.get("outgoing") if iterator else None
                outgoing_ids = set(outgoing) if outgoing else set()
                if current >= FRAMES:
                    break
            elif event == "draw-roster":
                ticks[current] = {
                    "room": room,
                    "outgoing": set(outgoing_ids),
                    "live": [(value["entity"], state_types[value["entity"]], value["Visible"], value["hudExcluded"])
                             for value in row["live"]],
                    "decals": {key: {"position": value["position"],
                                     "banner": any(component["type"] == "Banner" for component in value["components"])}
                               for key, value in state_entities.items() if value["type"] == "Decal"},
                }
            elif event == "draw-dispatch":
                if current in DIFFERENTIAL_TICKS:
                    ticks[current]["commands_by_owner"] = dict(commands)
                    commands = Counter()
                if current in INTRO_LAG_TICKS:
                    player_span = next(span for span in row["entities"] if span["type"] == "Player")
                    ticks[current]["player_current_depth"] = player_span["actualDepth"]
    return ticks


def source_room(entry_id, kind, room, outgoing):
    if kind == "Player" or kind in ("BackgroundTiles", "SolidTiles", "TotalStrawberriesDisplay") or kind == "ParticleSystem":
        return ""
    return "1" if entry_id in outgoing else room


def source_entries(source):
    entries = []
    for entry_id, kind, visible, hud in source["live"]:
        room = source_room(entry_id, kind, source["room"], source["outgoing"])
        entries.append((entry_id, kind, room, visible, hud))
    return entries


def source_keys(tick, source):
    keys = []
    ordinals = Counter()
    particle_seen = 0
    for _entry_id, kind, room, _visible, _hud in source_entries(source):
        if kind == "Decal":
            ordinal = ordinals[(kind, room)]
            layer = "bg" if ordinal < DECAL_BANDS[room][0] else "fg"
            index = ordinal if layer == "bg" else ordinal - DECAL_BANDS[room][0]
            keys.append(("Decal", room, layer, index))
        elif kind == "Spikes":
            keys.append(("Spikes", room, ROOM_OBJECTS[room]["Spikes"][ordinals[(kind, room)]]))
        elif kind in ("JumpthruPlatform", "Strawberry", "Spring"):
            keys.append((kind, room, ROOM_OBJECTS[room][kind][0]))
        elif kind == "ParticleSystem":
            keys.append(("ParticleSystem", PARTICLE_DEPTHS[particle_seen]))
            particle_seen += 1
        else:
            keys.append((kind, room))
        ordinals[(kind, room)] += 1
    return keys


def native_keys(roster):
    keys = []
    for owner in roster["live"]:
        kind = owner["kind"]
        if kind == "Decal":
            keys.append(("Decal", owner["room"], "bg" if owner["sortDepthBand"] > 0 else "fg", owner["authoredId"]))
        elif kind == "ParticleSystem":
            keys.append(("ParticleSystem", owner["sortDepthBand"]))
        elif kind in ("Player", "BackgroundTiles", "SolidTiles", "TotalStrawberriesDisplay"):
            keys.append((kind, ""))
        elif kind in ("Entity", "WindController"):
            keys.append((kind, owner["room"]))
        else:
            keys.append((kind, owner["room"], owner["authoredId"]))
    return keys


def load_native(path):
    rosters = {}
    dispatches = {}
    players = {}
    with path.open() as stream:
        for line in stream:
            if line.startswith('{"event":"draw-owner-roster"'):
                row = json.loads(line)
                rosters[row["tick"]] = row
            elif line.startswith('{"event":"draw-owner-dispatch"'):
                row = json.loads(line)
                dispatches[row["tick"]] = row["order"]
            elif line.startswith('{"event":"phase"') and '"after-frame"' in line:
                row = json.loads(line)
                players[row["tick"]] = row["state"]["player"]
    return rosters, dispatches, players


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compare_tick(tick, source, roster, dispatch, native_player_id, represented_rooms=frozenset({"1"})):
    entries = source_entries(source)
    expected_entries = [entry for entry in entries if entry[1] != "Decal" or entry[2] in represented_rooms]
    expected = [key for key in source_keys(tick, source) if key[0] != "Decal" or key[1] in represented_rooms]
    unrepresented = [key for key in source_keys(tick, source) if key[0] == "Decal" and key[1] not in represented_rooms]
    native = roster["live"]
    actual = native_keys(roster)
    identities = [owner["identity"] for owner in native]
    require(len(set(identities)) == len(identities), f"tick {tick}: native owner identities must be unique")
    require(len(set(actual)) == len(actual), f"tick {tick}: native semantic owner bindings must be unique")
    require(len(native) + len(unrepresented) == len(entries),
            f"tick {tick}: native live owners plus the reported gap must equal the SOURCE roster")
    require(sorted(roster["decalGapRooms"]) == sorted({key[1] for key in unrepresented}),
            f"tick {tick}: the decal gap must be reported for exactly the unrepresented room")
    require(actual == expected, f"tick {tick}: native draw owner chronology differs from the SOURCE roster")
    for owner, entry in zip(native, expected_entries):
        require(owner["visible"] == entry[3] and owner["hudExcluded"] == entry[4],
                f"tick {tick}: native visibility/HUD exclusion differs from SOURCE for {entry[1]}")
    dispatched = [owner for owner in native if owner["visible"] and not owner["hudExcluded"]]
    require(dispatch == [owner["identity"] for owner in dispatched],
            f"tick {tick}: native dispatch order differs from the visible non-HUD roster")
    players = [owner for owner in native if owner["kind"] == "Player"]
    require(len(players) == 1, f"tick {tick}: the Player owner must appear exactly once")
    require(players[0]["identity"] == native_player_id,
            f"tick {tick}: the Player draw owner must be the tracked native Player")
    expected_room1_decals = 29 if source["room"] == "1" or source["outgoing"] else 0
    require(sum(1 for owner in native if owner["kind"] == "Decal" and owner["room"] == "1") == expected_room1_decals,
            f"tick {tick}: the authored first-room decal owners must stay projected exactly while room 1 is live")
    return unrepresented


class NativeGameplayDrawProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native = canonical_root() / NATIVE_NAME
        fixtures = (SOURCE_TRACE, native)
        present = [path.is_file() for path in fixtures]
        if not any(present):
            raise unittest.SkipTest("Actual private SOURCE/native draw observations are unavailable")
        if not all(present):
            raise ValueError("Partial draw-ownership evidence: pinned private fixtures must stay consistent")
        if file_identity(SOURCE_TRACE) != SOURCE_IDENTITY:
            raise ValueError("Immutable accepted SOURCE draw trace changed")
        if file_identity(native) != NATIVE_IDENTITY:
            raise ValueError("Immutable native draw-owner trace changed")
        cls.source = sample_source(SOURCE_TRACE)
        cls.rosters, cls.dispatches, cls.players = load_native(native)
        require(sorted(cls.source) == list(range(FRAMES)), "The SOURCE trace must observe every route tick")
        require(sorted(cls.rosters) == list(range(FRAMES)), "The native trace must project every route tick")
        cls.native_path = native

    def compare(self, tick):
        return compare_tick(tick, self.source[tick], self.rosters[tick], self.dispatches[tick], self.players[tick])

    def test_every_route_tick_owner_chronology_matches_source(self):
        for tick in range(FRAMES):
            self.compare(tick)

    def test_tick0_full_roster_matches_source(self):
        self.assertEqual(self.compare(0), [])
        self.assertEqual(len(self.source[0]["live"]), 43)

    def test_tick375_supported_owners_match_source_with_reported_gap(self):
        self.assertEqual(len(self.compare(375)), 23)
        self.assertEqual(len(self.source[375]["live"]), 72)

    def test_post_unload_ticks_have_no_helper_and_player_before_wind(self):
        for tick in FOCUSED_POST_UNLOAD_TICKS:
            unrepresented = self.compare(tick)
            self.assertEqual(len(unrepresented), 23)
            keys = [key for key in source_keys(tick, self.source[tick]) if not (key[0] == "Decal" and key[1] == "2")]
            self.assertNotIn(("Entity", "1"), keys)
            self.assertNotIn(("Entity", "2"), keys)
            depth_zero = [owner["kind"] for owner in self.rosters[tick]["live"] if owner["sortDepthBand"] == 0]
            self.assertEqual(depth_zero, ["Player", "WindController"])

    def test_tick35_intro_placement_band_differs_from_source_current_depth(self):
        for tick, last in ((35, True), (36, False)):
            source_depth = self.source[tick]["player_current_depth"]
            band = next(owner["sortDepthBand"] for owner in self.rosters[tick]["live"]
                        if owner["kind"] == "Player")
            self.assertGreater(source_depth, -0.001)
            self.assertEqual(band, -1000000 if tick == 35 else 0)
            dispatched = self.dispatches[tick]
            player = next(owner["identity"] for owner in self.rosters[tick]["live"]
                          if owner["kind"] == "Player")
            self.assertEqual(dispatched[-1] == player, last)

    def test_player_intro_depth_then_transition_depth(self):
        players0 = [owner for owner in self.rosters[0]["live"] if owner["kind"] == "Player"]
        players375 = [owner for owner in self.rosters[375]["live"] if owner["kind"] == "Player"]
        self.assertEqual(players0[0]["sortDepthBand"], -1000000)
        self.assertEqual(players375[0]["sortDepthBand"], 0)

    def test_hud_owner_is_excluded_from_dispatch(self):
        roster = self.rosters[0]
        hud = [owner for owner in roster["live"] if owner["kind"] == "TotalStrawberriesDisplay"]
        self.assertEqual(len(hud), 1)
        self.assertFalse(hud[0]["visible"])
        self.assertTrue(hud[0]["hudExcluded"])
        self.assertNotIn(hud[0]["identity"], self.dispatches[0])

    def test_spring_uses_source_draw_depth(self):
        springs = [owner for owner in self.rosters[375]["live"] if owner["kind"] == "Spring"]
        self.assertEqual(len(springs), 1)
        self.assertEqual(springs[0]["sortDepthBand"], -8501)

    def test_outgoing_owners_match_the_source_window(self):
        for tick in OUTGOING_WINDOW:
            source = self.source[tick]
            require(len(source["outgoing"]) > 0, f"tick {tick}: SOURCE outgoing owners must be live")
            roster = self.rosters[tick]
            room1 = [owner for owner in roster["live"] if owner["room"] == "1"]
            self.assertEqual(len(room1), 35)
            self.assertEqual(roster["decalGapRooms"], ["2"])
        require(len(self.source[413]["outgoing"]) == 0, "SOURCE outgoing owners must be unloaded at tick 413")
        self.assertEqual(self.source[413]["room"], "2")
        self.assertFalse(any(owner["room"] == "1" for owner in self.rosters[413]["live"]))

    def test_source_command_facts_still_match_the_accepted_receipt(self):
        for tick in DIFFERENTIAL_TICKS:
            self.assertEqual(self.source[tick]["commands_by_owner"], ANNOUNCED_COMMANDS[tick])

    def test_dropped_decal_owner_is_rejected(self):
        changed = copy.deepcopy(self.rosters[0])
        decal = next(owner for owner in changed["live"] if owner["kind"] == "Decal")
        changed["live"].remove(decal)
        with self.assertRaisesRegex(ValueError, "gap must equal|chronology"):
            compare_tick(0, self.source[0], changed, self.dispatches[0], self.players[0])

    def test_same_kind_distinct_owner_swap_is_rejected(self):
        changed = copy.deepcopy(self.rosters[0])
        live = changed["live"]
        decals = [index for index, owner in enumerate(live) if owner["kind"] == "Decal" and owner["sortDepthBand"] > 0]
        first, second = decals[3], decals[4]
        live[first], live[second] = live[second], live[first]
        dispatched = [owner["identity"] for owner in live if owner["visible"] and not owner["hudExcluded"]]
        with self.assertRaisesRegex(ValueError, "chronology"):
            compare_tick(0, self.source[0], changed, dispatched, self.players[0])

    def test_identity_alias_is_rejected(self):
        changed = copy.deepcopy(self.rosters[0])
        live = changed["live"]
        decals = [owner for owner in live if owner["kind"] == "Decal"]
        decals[5]["identity"] = decals[6]["identity"]
        dispatched = [owner["identity"] for owner in live if owner["visible"] and not owner["hudExcluded"]]
        with self.assertRaisesRegex(ValueError, "identities must be unique"):
            compare_tick(0, self.source[0], changed, dispatched, self.players[0])

    def test_visibility_flap_is_rejected(self):
        changed = copy.deepcopy(self.rosters[0])
        next(owner for owner in changed["live"] if owner["kind"] == "TotalStrawberriesDisplay")["visible"] = True
        with self.assertRaisesRegex(ValueError, "visibility/HUD"):
            compare_tick(0, self.source[0], changed, self.dispatches[0], self.players[0])

    def test_reordering_is_rejected(self):
        changed = copy.deepcopy(self.rosters[375])
        live = changed["live"]
        spring = next(owner for owner in live if owner["kind"] == "Spring")
        index = live.index(spring)
        live.insert(index - 2, live.pop(index))
        dispatched = [owner["identity"] for owner in live if owner["visible"] and not owner["hudExcluded"]]
        with self.assertRaisesRegex(ValueError, "chronology"):
            compare_tick(375, self.source[375], changed, dispatched, self.players[375])

    def test_hidden_gap_is_rejected(self):
        changed = copy.deepcopy(self.rosters[375])
        changed["decalGapRooms"] = []
        with self.assertRaisesRegex(ValueError, "decal gap"):
            compare_tick(375, self.source[375], changed, self.dispatches[375], self.players[375])

    def test_duplicated_player_is_rejected(self):
        changed = copy.deepcopy(self.rosters[375])
        player = next(owner for owner in changed["live"] if owner["kind"] == "Player")
        changed["live"].append(copy.deepcopy(player))
        dispatched = [owner["identity"] for owner in changed["live"] if owner["visible"] and not owner["hudExcluded"]]
        with self.assertRaisesRegex(ValueError, "chronology|unique|exactly once"):
            compare_tick(375, self.source[375], changed, dispatched, self.players[375])


if __name__ == "__main__":
    unittest.main()
