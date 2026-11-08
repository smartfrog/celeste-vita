#pragma once

#include "player.hpp"
#include "presentation.hpp"
#include <array>
#include <string>
#include <string_view>

namespace celeste::diagnostic {

struct MaskData {
    int x, y, columns, rows;
    std::vector<std::uint8_t> cells;
};

struct TextureInfo {
    int width, height, crop_width, crop_height, trim_x, trim_y, frame_width, frame_height;
    std::uint32_t checksum;
};
struct TileCommand {
    bool background;
    int texture, x, y, u, v;
};
struct SpikePiece {
    bool up;
    int x, y, width, height, u, v;
};
struct VisualAssets {
    static constexpr int body_texture = 5;
    static constexpr int up_texture = 6;
    static constexpr int left_texture = 7;
    std::array<TextureInfo,8> textures;
    int texture_count = 0;
    std::vector<TileCommand> commands;
    std::vector<SpikePiece> spike_pieces;
    bool spike_art() const { return texture_count == 8; }
};
struct PlayerAssets {
    PlayerFrameBank bank;
    std::vector<std::uint32_t> checksums;
};

std::uint32_t checksum(std::string_view text);
MaskData parse_mask(std::string_view text, std::uint32_t expected_checksum);
std::vector<StaticSpike> parse_spikes(std::string_view text, std::uint32_t expected_checksum);
VisualAssets parse_visuals(std::string_view text, std::uint32_t expected_checksum);
void validate_spike_art(const VisualAssets& visuals, const std::vector<StaticSpike>& spikes);
PlayerAssets parse_player_assets(std::string_view text, std::uint32_t expected_checksum);
void validate_texture_bytes(std::string_view bytes, const TextureInfo& texture);
std::string read_asset(const char* path, std::size_t limit);

class Room final {
public:
    Room(MaskData mask, std::vector<StaticSpike> spikes);
    Room(const Room&) = delete;
    Room& operator=(const Room&) = delete;
    const TileGrid grid;
    Body solids;
    const std::vector<StaticSpike> spikes;
    const PlayerWorld world;
};

}
