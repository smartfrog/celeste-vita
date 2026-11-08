#include "assets.hpp"
#include <charconv>
#include <cstring>
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
std::uint32_t hex_value(std::string_view text) {
    std::uint32_t value=0;
    if(text.size()!=8 || text.find_first_not_of("0123456789abcdef")!=std::string_view::npos)
        throw std::invalid_argument("Invalid asset hexadecimal field");
    const auto parsed=std::from_chars(text.data(),text.data()+text.size(),value,16);
    if(parsed.ec!=std::errc{} || parsed.ptr!=text.data()+text.size()) throw std::invalid_argument("Invalid asset hexadecimal field");
    return value;
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
VisualAssets parse_visuals(std::string_view text, std::uint32_t expected_checksum) {
    integrity(text,65'536,expected_checksum);
    header(text,"CSRV1");
    if (take(text) != "6") throw std::invalid_argument("Expected six bounded room textures");
    VisualAssets result{};
    for (std::size_t i=0; i<result.textures.size(); ++i) {
        auto row = take(text);
        auto& t = result.textures[i];
        for (auto field : {&t.width,&t.height,&t.crop_width,&t.crop_height,&t.trim_x,&t.trim_y,&t.frame_width,&t.frame_height})
            *field = integer(take(row,' '));
        t.checksum=hex_value(row);
        if (i < 5 ? (t.width != 64 || t.height != 128 || t.crop_width != 48 || t.crop_height != 120 ||
                     t.trim_x != 0 || t.trim_y != 0 || t.frame_width != 48 || t.frame_height != 120) :
                    (t.width != 16 || t.height != 16 || t.crop_width <= 0 || t.crop_width > 14 ||
                     t.crop_height <= 0 || t.crop_height > 14 || t.frame_width != 32 || t.frame_height != 32 ||
                     t.trim_x < 0 || t.trim_x > 32-t.crop_width || t.trim_y < 0 || t.trim_y > 32-t.crop_height))
            throw std::invalid_argument("Unsupported bounded texture profile");
    }
    const int count = integer(take(text));
    if (count < 0 || count > 1840) throw std::invalid_argument("Excessive room commands");
    std::array<bool,1840> occupied{};
    bool foreground = false;
    for (int i=0; i<count; ++i) {
        auto row = take(text);
        const auto layer = take(row,' ');
        TileCommand command{};
        command.background = layer == "B";
        command.texture = integer(take(row,' '));
        command.x = integer(take(row,' ')); command.y = integer(take(row,' '));
        command.u = integer(take(row,' ')); command.v = integer(row);
        if ((layer != "B" && layer != "F") || (foreground && command.background) ||
            command.texture < 0 || command.texture >= 5 || (command.background ? command.texture != 4 : command.texture == 4) ||
            command.x < 0 || command.x >= 320 || command.x%8 || command.y < 0 || command.y > 176 || command.y%8 ||
            command.u < 0 || command.u > 40 || command.u%8 || command.v < 0 || command.v > 112 || command.v%8)
            throw std::invalid_argument("Invalid room layer/texture/command bounds");
        foreground = !command.background;
        const auto cell = (command.background ? 0 : 920)+command.y/8*40+command.x/8;
        if (occupied[cell]) throw std::invalid_argument("Duplicate room layer cell");
        occupied[cell] = true;
        result.commands.push_back(command);
    }
    if (!text.empty()) throw std::invalid_argument("Trailing room commands");
    return result;
}
PlayerAssets parse_player_assets(std::string_view text, std::uint32_t expected_checksum) {
    integrity(text,65'536,expected_checksum);
    header(text,"CSPP1");
    PlayerAssets result;
    const int pages=integer(take(text));
    if(pages<1 || pages>10) throw std::invalid_argument("Invalid player page count");
    result.bank.pages=unsigned(pages);
    for(int i=0;i<pages;++i) result.checksums.push_back(hex_value(take(text)));
    const int frames=integer(take(text));
    if(frames<1 || frames>256) throw std::invalid_argument("Invalid player frame count");
    for(int i=0;i<frames;++i) {
        auto row=take(text);
        PlayerFrame frame{};
        frame.name=take(row,' ');
        if(frame.name.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/")!=std::string::npos)
            throw std::invalid_argument("Invalid player frame identity");
        frame.page=unsigned(integer(take(row,' ')));
        for(auto field:{&frame.u,&frame.v,&frame.width,&frame.height,&frame.trim_x,&frame.trim_y,&frame.frame_width,&frame.frame_height})
            *field=integer(take(row,' '));
        frame.hair_offset.x=float(integer(take(row,' '))); frame.hair_offset.y=float(integer(take(row,' ')));
        frame.hair_frame=integer(take(row,' '));
        if(row!="0" && row!="1") throw std::invalid_argument("Invalid hair visibility");
        frame.has_hair=row=="1";
        result.bank.frames.push_back(std::move(frame));
    }
    if(integer(take(text))!=24) throw std::invalid_argument("Expected bounded 24-animation closure");
    for(int i=0;i<24;++i) {
        auto row=take(text);
        PlayerAnimation animation;
        animation.id=take(row,' ');
        const auto delay=hex_value(take(row,' '));
        std::memcpy(&animation.delay,&delay,sizeof delay);
        animation.next=take(row,' ');
        if(animation.next=="-") animation.next.clear();
        const int count=integer(take(row,' '));
        if(count<1 || count>32) throw std::invalid_argument("Invalid animation frame count");
        for(int f=0;f<count;++f) animation.frames.push_back(unsigned(integer(f==count-1 ? row : take(row,' '))));
        result.bank.animations.push_back(std::move(animation));
    }
    auto row=take(text);
    for(auto& frame:result.bank.bangs) frame=unsigned(integer(take(row,' ')));
    result.bank.hair=unsigned(integer(row));
    if(!text.empty()) throw std::invalid_argument("Trailing player presentation metadata");
    result.bank.validate();
    return result;
}
void validate_texture_bytes(std::string_view bytes, const TextureInfo& texture) {
    if (texture.width <= 0 || texture.height <= 0 || texture.width > 64 || texture.height > 128 ||
        bytes.size() != std::size_t(texture.width)*texture.height*4 || checksum(bytes) != texture.checksum)
        throw std::invalid_argument("Texture byte count or build-pinned integrity mismatch");
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
