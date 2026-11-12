"""Restricted DX9 effect metadata reader; no shader execution or GPU access."""

import hashlib
from pathlib import Path
import struct
import zipfile
from native_room_revision import file_identity

ARCHIVE = Path("/home/fred/projects/celeste-vita/game/celeste-linux.zip")
ARCHIVE_SHA = "a613430411dbef3c0c45a0474f90f4845122964c7d177d69e88965bcb84741bf"
RESOURCE_SHA = {
    "Dither": "4e572804560609ef9a3e035a3f7fe6dc8b3802ebcee1dbeb05d1552b9813bf4d",
    "Primitive": "37b3975f2d860d95bbbb7ce7a4e7233c3e0508bd672627c967d63768de005c6f",
}
GAUSSIAN_SHA = "4bc39e8b3498a87c6143e601cd2894e06522c42e7262a54e7cf1bbfb37240944"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def uint(data, offset):
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("Truncated effect metadata")
    return struct.unpack_from("<I", data, offset)[0]


def string(data, offset):
    if offset < 0 or offset >= len(data):
        raise ValueError("Invalid effect string offset")
    end = data.find(b"\0", offset)
    if end < 0:
        raise ValueError("Unterminated effect string")
    return data[offset:end].decode("ascii")


def shader_contract(data):
    version = uint(data, 0)
    if version not in (0xFFFF0200, 0xFFFF0300, 0xFFFE0300):
        raise ValueError("Excluded shader version")
    constants = {}
    offset = 4
    ended = False
    while offset < len(data):
        token = uint(data, offset)
        offset += 4
        opcode = token & 0xFFFF
        if opcode == 0xFFFF:
            ended = True
            break
        if opcode == 0xFFFE:
            count = (token >> 16) & 0x7FFF
            body = data[offset:offset + count * 4]
            if len(body) != count * 4:
                raise ValueError("Truncated shader comment")
            if body[:4] == b"CTAB":
                table = body[4:]
                if uint(table, 0) != 28:
                    raise ValueError("Excluded shader constant table")
                for index in range(uint(table, 12)):
                    entry = uint(table, 16) + index * 20
                    name = string(table, uint(table, entry))
                    register_set, register, register_count, reserved = struct.unpack_from("<4H", table, entry + 4)
                    type_offset = uint(table, entry + 12)
                    parameter_class, parameter_type, rows, columns, elements, members = struct.unpack_from("<6H", table, type_offset)
                    if members or name in constants:
                        raise ValueError("Excluded shader constant layout")
                    constants[name] = {"register_set": register_set, "register": register,
                                       "register_count": register_count, "class": parameter_class,
                                       "type": parameter_type, "rows": rows, "columns": columns, "elements": elements,
                                       "reserved": reserved}
            offset += count * 4
        else:
            count = (token >> 24) & 15
            if count == 0:
                raise ValueError("Excluded zero-length shader instruction")
            offset += count * 4
    if not ended or offset != len(data):
        raise ValueError("Invalid shader termination")
    return {"stage": "pixel" if version >> 16 == 0xFFFF else "vertex",
            "version": version, "bytes": len(data), "sha256": digest(data), "constants": constants}


def parse_effect(name, resource):
    expected = GAUSSIAN_SHA if name == "GaussianBlur" else RESOURCE_SHA.get(name)
    if expected is None or digest(resource) != expected:
        raise ValueError("Unverified effect resource identity")
    start = resource.find(b"\x01\x09\xff\xfe")
    if start < 0 or resource[:6] != b"XNBw\x05\x01" or uint(resource, 6) != len(resource):
        raise ValueError("Excluded effect container")
    data = resource[start:]
    table = uint(data, 4) + 8
    parameter_count, technique_count, _, object_count = struct.unpack_from("<4I", data, table)
    cursor = table + 16

    def effect_string(relative):
        size = uint(data, 8 + relative)
        value = string(data, 12 + relative)
        if size != len(value) + 1:
            raise ValueError("Invalid effect string length")
        return value

    def parameter_type(relative):
        offset = relative + 8
        kind, category, name_offset, semantic, elements = struct.unpack_from("<5I", data, offset)
        if semantic or elements or category not in (0, 1, 2, 4):
            raise ValueError("Excluded effect parameter type")
        rows, columns = (uint(data, offset + 24), uint(data, offset + 20)) if category in (0, 1, 2) else (0, 0)
        return {"type": kind, "class": category, "name": effect_string(name_offset) if name_offset else "",
                "rows": rows, "columns": columns, "elements": elements, "type_offset": offset}

    parameters = {}
    for _ in range(parameter_count):
        type_offset, value_offset, flags, annotations = struct.unpack_from("<4I", data, cursor)
        cursor += 16
        item = parameter_type(type_offset)
        if flags or annotations or item["name"] in parameters:
            raise ValueError("Excluded effect parameter annotations")
        item["value_offset"] = value_offset + 8
        if item["type"] == 3 and item["class"] in (0, 1, 2):
            count = item["rows"] * item["columns"]
            item["default_float32_bits"] = list(struct.unpack_from("<" + "i" * count, data, value_offset + 8))
        elif item["type"] == 5 and item["class"] == 4:
            item["default_texture_object"] = uint(data, value_offset + 8)
        elif item["type"] == 10 and item["class"] == 4 and uint(data, value_offset + 8) == 0:
            item["default_sampler_states"] = []
        else:
            raise ValueError("Excluded effect parameter default")
        parameters[item.pop("name")] = item
    techniques = {}
    ordered = []
    for _ in range(technique_count):
        name_offset, annotations, pass_count = struct.unpack_from("<3I", data, cursor)
        cursor += 12
        technique = effect_string(name_offset)
        if annotations or technique in techniques:
            raise ValueError("Excluded effect technique annotations")
        passes = []
        for _ in range(pass_count):
            pass_name, annotations, state_count = struct.unpack_from("<3I", data, cursor)
            cursor += 12
            if annotations:
                raise ValueError("Excluded effect pass annotations")
            states = []
            for _ in range(state_count):
                operation, index, type_offset, value_offset = struct.unpack_from("<4I", data, cursor)
                cursor += 16
                if operation not in (146, 147) or index:
                    raise ValueError("Excluded effect render state")
                states.append({"operation": operation, "object": uint(data, value_offset + 8),
                               "type": parameter_type(type_offset), "program": None})
            passes.append({"name": effect_string(pass_name), "states": states, "programs": []})
        techniques[technique] = passes
        ordered.append(passes)
    small, large = struct.unpack_from("<2I", data, cursor)
    cursor += 8
    empty_objects = []
    for _ in range(small):
        object_index, size = struct.unpack_from("<2I", data, cursor)
        cursor += 8
        if object_index >= object_count or size:
            raise ValueError("Excluded effect small object")
        empty_objects.append(object_index)
    if any(item["default_texture_object"] not in empty_objects for item in parameters.values() if "default_texture_object" in item):
        raise ValueError("Unresolved default texture object")
    for _ in range(large):
        technique, pass_index, unknown, state_index, kind, size = struct.unpack_from("<6I", data, cursor)
        cursor += 24
        if unknown != 0xFFFFFFFF or kind:
            raise ValueError("Excluded effect shader object")
        program = shader_contract(data[cursor:cursor + size])
        program["effect_byte_offset"] = cursor
        state = ordered[technique][pass_index]["states"][state_index]
        if state["operation"] != (146 if program["stage"] == "vertex" else 147) or state["program"] is not None:
            raise ValueError("Effect shader stage mismatch")
        state["program"] = program["sha256"]
        ordered[technique][pass_index]["programs"].append(program)
        cursor += (size + 3) & ~3
    if cursor != len(data) or any(state["program"] is None for passes in ordered for item in passes for state in item["states"]):
        raise ValueError("Unresolved effect shader objects")
    return {"resource": "Content/Effects/" + name + ".xnb", "resource_sha256": digest(resource),
            "effect_offset": start, "effect_sha256": digest(data), "parameters": parameters, "techniques": techniques}


def original_effects(archive=ARCHIVE):
    if file_identity(archive)["sha256"] != ARCHIVE_SHA:
        raise ValueError("Pinned original archive identity changed")
    with zipfile.ZipFile(archive) as package:
        return {name: parse_effect(name, package.read("Content/Effects/" + name + ".xnb")) for name in RESOURCE_SHA}


def gaussian_effect(archive=ARCHIVE):
    if file_identity(archive)["sha256"] != ARCHIVE_SHA:
        raise ValueError("Pinned original archive identity changed")
    with zipfile.ZipFile(archive) as package:
        return parse_effect("GaussianBlur", package.read("Content/Effects/GaussianBlur.xnb"))
