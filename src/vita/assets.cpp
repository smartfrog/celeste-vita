#include "assets.hpp"
#include <charconv>
#include <cstdio>
#include <limits>
#include <memory>
#include <stdexcept>

namespace celeste::diagnostic {
namespace {
constexpr std::string_view input_sha = "fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe";
constexpr std::string_view map_sha = "ace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab";

std::string_view take(std::string_view& text, char separator = '\n') {
    const auto end = text.find(separator);
    if (end == std::string_view::npos) throw std::invalid_argument("Truncated asset field");
    auto field = text.substr(0, end);
    text.remove_prefix(end + 1);
    return field;
}
int integer(std::string_view text) {
    int value = 0;
    auto parsed = std::from_chars(text.data(), text.data()+text.size(), value);
    if (parsed.ec != std::errc{} || parsed.ptr != text.data()+text.size() || std::to_string(value) != text)
        throw std::invalid_argument("Invalid or noncanonical asset integer");
    return value;
}
void header(std::string_view& text, std::string_view version) {
    if (take(text) != version || take(text) != input_sha || take(text) != map_sha)
        throw std::invalid_argument("Wrong asset version or pinned input hashes");
}
void integrity(std::string_view text, std::size_t limit, std::uint32_t expected) {
    if (text.size() > limit || checksum(text) != expected)
        throw std::invalid_argument("Asset exceeds bound or fails build-pinned FNV-1a integrity");
}
PlayerWorld make_world(Body& solids, const std::vector<StaticSpike>& spikes) {
    PlayerWorld world{};
    world.collision.solids.push_back(&solids);
    world.safe_ground.push_back(&solids);
    world.bounds_left = 0;
    world.bounds_right = 320;
    for (const auto& spike : spikes) world.spikes.push_back(&spike);
    return world;
}
}

std::uint32_t checksum(std::string_view text) {
    std::uint32_t hash = 2166136261u;
    for (unsigned char byte : text) hash = (hash ^ byte) * 16777619u;
    return hash;
}
MaskData parse_mask(std::string_view text, std::uint32_t expected_checksum) {
    integrity(text, 4'000'512, expected_checksum);
    header(text, "CSTM1");
    auto dimensions = take(text);
    MaskData mask;
    mask.x = integer(take(dimensions, ' '));
    mask.y = integer(take(dimensions, ' '));
    mask.columns = integer(take(dimensions, ' '));
    mask.rows = integer(dimensions);
    const auto count = std::int64_t(mask.columns) * mask.rows;
    if (mask.columns <= 0 || mask.rows <= 0 || count > 4'000'000)
        throw std::invalid_argument("Invalid mask dimensions");
    for (auto edge : {std::int64_t(mask.columns)*8, std::int64_t(mask.rows)*8,
                     mask.x + std::int64_t(mask.columns)*8, mask.y + std::int64_t(mask.rows)*8}) {
        if (edge < std::numeric_limits<std::int32_t>::min() || edge > std::numeric_limits<std::int32_t>::max())
            throw std::invalid_argument("Mask edge overflow");
    }
    const auto cells = take(text);
    if (!text.empty() || cells.size() != static_cast<std::size_t>(count))
        throw std::invalid_argument("Wrong mask cell length or trailing data");
    mask.cells.reserve(cells.size());
    for (char cell : cells) {
        if (cell != '0' && cell != '1') throw std::invalid_argument("Nonbinary mask cell");
        mask.cells.push_back(cell - '0');
    }
    return mask;
}
std::vector<StaticSpike> parse_spikes(std::string_view text, std::uint32_t expected_checksum) {
    integrity(text, 8192, expected_checksum);
    header(text, "CSH1");
    const auto count = integer(take(text));
    if (count < 0 || count > 64) throw std::invalid_argument("Invalid spike count");
    std::vector<StaticSpike> spikes;
    spikes.reserve(count);
    for (int i = 0; i < count; ++i) {
        auto row = take(text);
        auto direction = take(row, ' ');
        const int x = integer(take(row, ' ')), y = integer(take(row, ' ')), size = integer(row);
        if ((direction != "up" && direction != "left") || x < -1'000'000 || x > 1'000'000 ||
            y < -1'000'000 || y > 1'000'000 || size <= 0 || size > 1'000'000)
            throw std::invalid_argument("Unsupported or out-of-bounds diagnostic spike");
        spikes.emplace_back(Vec2{static_cast<float>(x), static_cast<float>(y)}, size,
                            direction == "up" ? SpikeDirection::up : SpikeDirection::left);
    }
    if (!text.empty()) throw std::invalid_argument("Trailing spike data");
    return spikes;
}
std::string read_asset(const char* path, std::size_t limit) {
    const auto close_file = [](FILE* file) { std::fclose(file); };
    std::unique_ptr<FILE, decltype(close_file)> file(std::fopen(path, "rb"), close_file);
    if (!file) throw std::runtime_error(std::string("Cannot open asset: ") + path);
    std::string text;
    char buffer[4096];
    while (const auto count = std::fread(buffer, 1, sizeof(buffer), file.get())) {
        if (text.size() + count > limit) {
            const int closed = std::fclose(file.release());
            throw std::runtime_error(std::string("Asset exceeds bound: ") + path + (closed ? "; close failed" : ""));
        }
        text.append(buffer, count);
    }
    const bool failed = std::ferror(file.get());
    const int closed = std::fclose(file.release());
    if (failed || closed) throw std::runtime_error(std::string("Asset read/close failed: ") + path);
    return text;
}
Room::Room(MaskData mask, std::vector<StaticSpike> hazards)
    : grid(mask.columns, mask.rows, std::move(mask.cells)),
      solids{{static_cast<float>(mask.x),static_cast<float>(mask.y)}, std::nullopt, true, &grid},
      spikes(std::move(hazards)), world(make_world(solids, spikes)) {}
}
