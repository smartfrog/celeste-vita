"""Fixed 128x64 private player pages; deduplicate exact crops, never omit frames."""

from native_room_textures import extrude


def pack_player_crops(crops):
    if not crops or len(crops) > 256:
        raise ValueError("Invalid bounded player crop count")
    unique, aliases = {}, {}
    for name, (width, height, rgba) in crops.items():
        if not 1 <= width <= 126 or not 1 <= height <= 62 or len(rgba) != width * height * 4:
            raise ValueError("Invalid player crop dimensions or bytes")
        key = width, height, rgba
        aliases[name] = unique.setdefault(key, name)
    pages, layout = [bytearray(128 * 64 * 4)], {}
    x = y = row_height = 0
    for (width, height, rgba), name in sorted(unique.items(), key=lambda entry: (-entry[0][1], -entry[0][0], entry[1])):
        if x + width + 2 > 128:
            x, y, row_height = 0, y + row_height, 0
        if y + height + 2 > 64:
            if len(pages) == 10:
                raise ValueError("Required player closure exceeds fixed page upload budget")
            pages.append(bytearray(128 * 64 * 4))
            x = y = row_height = 0
        padded = extrude(rgba, width, height, width + 2, height + 2)
        for dy in range(height + 2):
            target = ((y + dy) * 128 + x) * 4
            start = dy * (width + 2) * 4
            pages[-1][target:target + (width + 2) * 4] = padded[start:start + (width + 2) * 4]
        layout[name] = len(pages) - 1, x + 1, y + 1
        x, row_height = x + width + 2, max(row_height, height + 2)
    return [bytes(page) for page in pages], {name: layout[target] for name, target in aliases.items()}
