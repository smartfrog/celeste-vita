#include "assets.hpp"
#include "asset_text.hpp"
#include <algorithm>
#include <charconv>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <limits>
#include <memory>
#include <stdexcept>

namespace celeste::diagnostic {
namespace {
constexpr std::string_view input_sha = "fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe";
constexpr std::string_view map_sha = "ace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab";

using asset_text::take;
using asset_text::integer;
using asset_text::integrity;
void header(std::string_view& text, std::string_view version) {
    if (take(text) != version || take(text) != input_sha || take(text) != map_sha)
        throw std::invalid_argument("Wrong asset version or pinned input hashes");
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
    return asset_text::checksum(text);
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
    const auto version = take(text);
    if (version != "CSRV1" && version != "CSRV2")
        throw std::invalid_argument("Wrong visual asset version");
    if (take(text) != input_sha || take(text) != map_sha)
        throw std::invalid_argument("Wrong asset version or pinned input hashes");
    VisualAssets result{};
    result.texture_count = integer(take(text));
    if (result.texture_count != (version == "CSRV1" ? 6 : 8))
        throw std::invalid_argument("Unexpected bounded room texture count");
    for (int i=0; i<result.texture_count; ++i) {
        auto row = take(text);
        auto& t = result.textures[i];
        for (auto field : {&t.width,&t.height,&t.crop_width,&t.crop_height,&t.trim_x,&t.trim_y,&t.frame_width,&t.frame_height})
            *field = integer(take(row,' '));
        t.checksum=hex_value(row);
        const bool valid = i < 5 ? (t.width == 64 && t.height == 128 && t.crop_width == 48 && t.crop_height == 120 &&
                                    t.trim_x == 0 && t.trim_y == 0 && t.frame_width == 48 && t.frame_height == 120) :
                           i == 5 ? (t.width == 16 && t.height == 16 && t.crop_width > 0 && t.crop_width <= 14 &&
                                     t.crop_height > 0 && t.crop_height <= 14 && t.frame_width == 32 && t.frame_height == 32 &&
                                     t.trim_x >= 0 && t.trim_x <= 32-t.crop_width && t.trim_y >= 0 && t.trim_y <= 32-t.crop_height) :
                           i == VisualAssets::up_texture ? (t.width == 16 && t.height == 16 && t.crop_width == 7 &&
                                                            t.crop_height == 6 && t.trim_x == 1 && t.trim_y == 1 &&
                                                            t.frame_width == 7 && t.frame_height == 6) :
                           (t.width == 16 && t.height == 16 && t.crop_width == 6 && t.crop_height == 7 &&
                            t.trim_x == 1 && t.trim_y == 1 && t.frame_width == 6 && t.frame_height == 7);
        if (!valid) throw std::invalid_argument("Unsupported bounded texture profile");
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
    if (version == "CSRV2") {
        const int families = integer(take(text));
        if (families != 2) throw std::invalid_argument("Expected two singleton spike families");
        bool up = false, left = false;
        for (int i=0; i<families; ++i) {
            auto row = take(text);
            const auto name = take(row,' ');
            if (integer(row) != 1 || ((name == "default_up") ? up : (name == "default_left") ? left : true))
                throw std::invalid_argument("Spike family is not the pinned singleton");
            (name == "default_up" ? up : left) = true;
        }
        if (!up || !left) throw std::invalid_argument("Missing pinned spike family");
        const int pieces = integer(take(text));
        if (pieces < 1 || pieces > 64) throw std::invalid_argument("Invalid spike piece count");
        for (int i=0; i<pieces; ++i) {
            auto row = take(text);
            const auto direction = take(row,' ');
            SpikePiece piece{};
            piece.up = direction == "up";
            piece.x = integer(take(row,' ')); piece.y = integer(take(row,' '));
            piece.width = integer(take(row,' ')); piece.height = integer(take(row,' '));
            piece.u = integer(take(row,' ')); piece.v = integer(row);
            if ((direction != "up" && direction != "left") ||
                piece.x < -1'000'000 || piece.x > 1'000'000 || piece.y < -1'000'000 || piece.y > 1'000'000 ||
                piece.width != (piece.up ? 7 : 6) || piece.height != (piece.up ? 6 : 7) ||
                piece.u != 1 || piece.v != 1)
                throw std::invalid_argument("Invalid spike image piece");
            result.spike_pieces.push_back(piece);
        }
    }
    if (!text.empty()) throw std::invalid_argument("Trailing room commands");
    return result;
}

void validate_spike_art(const VisualAssets& visuals, const std::vector<StaticSpike>& spikes) {
    if (!visuals.spike_art()) throw std::invalid_argument("Spike art requires the optional eight-texture protocol");
    std::vector<SpikePiece> expected;
    for (const auto& spike : spikes) {
        const auto& box = spike.body().collider.value();
        const auto position = spike.body().position;
        const int pieces = static_cast<int>(spike.direction() == SpikeDirection::up ? box.width : box.height)/8;
        for (int i=0; i<pieces; ++i) {
            expected.push_back(spike.direction() == SpikeDirection::up
                ? SpikePiece{true, static_cast<int>(position.x)+8*i, static_cast<int>(position.y)-5, 7, 6, 1, 1}
                : SpikePiece{false, static_cast<int>(position.x)-5, static_cast<int>(position.y)+1+8*i, 6, 7, 1, 1});
        }
    }
    if (expected.size() != visuals.spike_pieces.size())
        throw std::invalid_argument("Spike source image piece count differs from hazard size/8");
    for (std::size_t i=0; i<expected.size(); ++i) {
        const auto& want = expected[i];
        const auto& have = visuals.spike_pieces[i];
        if (want.up != have.up || want.x != have.x || want.y != have.y || want.width != have.width ||
            want.height != have.height || want.u != have.u || want.v != have.v)
            throw std::invalid_argument("Spike source image placement differs from actual hazards");
    }
}
DecalAssets parse_decals(std::string_view text, std::uint32_t expected_checksum) {
    integrity(text, 65'536, expected_checksum);
    header(text, "CSD1");
    if (integer(take(text)) != 1) throw std::invalid_argument("Expected one bounded decal page");
    auto dimensions = take(text);
    if (integer(take(dimensions, ' ')) != DecalAssets::page_width || integer(take(dimensions, ' ')) != DecalAssets::page_height)
        throw std::invalid_argument("Unexpected decal page dimensions");
    DecalAssets result{};
    result.page_checksum = hex_value(dimensions);
    if (result.page_checksum == 0) throw std::invalid_argument("Invalid decal page checksum");
    result.texture_count = integer(take(text));
    if (result.texture_count != 15) throw std::invalid_argument("Expected fifteen static decal textures");
    const auto valid_name = [](std::string_view name) {
        return !name.empty() && name.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/-") == std::string_view::npos;
    };
    for (int i=0; i<result.texture_count; ++i) {
        auto row = take(text);
        auto& texture = result.textures[i];
        texture.name = std::string(take(row, ' '));
        if (!valid_name(texture.name)) throw std::invalid_argument("Invalid decal texture identity");
        for (int j=0; j<i; ++j)
            if (result.textures[j].name == texture.name) throw std::invalid_argument("Duplicate decal texture identity");
        texture.u = integer(take(row, ' ')); texture.v = integer(take(row, ' '));
        texture.width = integer(take(row, ' ')); texture.height = integer(take(row, ' '));
        texture.offset_x = integer(take(row, ' ')); texture.offset_y = integer(take(row, ' '));
        texture.frame_width = integer(take(row, ' ')); texture.frame_height = integer(row);
        const std::int64_t crop_right = std::int64_t(texture.u) + texture.width;
        const std::int64_t crop_bottom = std::int64_t(texture.v) + texture.height;
        if (texture.u < 1 || texture.v < 1 || texture.width <= 0 || texture.height <= 0 ||
            crop_right >= DecalAssets::page_width || crop_bottom >= DecalAssets::page_height ||
            texture.frame_width <= 0 || texture.frame_height <= 0 || texture.offset_x < -4096 || texture.offset_x > 4096 ||
            texture.offset_y < -4096 || texture.offset_y > 4096)
            throw std::invalid_argument("Invalid decal crop/page/frame geometry");
    }
    const int instances = integer(take(text));
    if (instances != 22) throw std::invalid_argument("Expected twenty-two static decal instances");
    bool foreground = false;
    std::array<bool,32> seen_background{}, seen_foreground{};
    for (int i=0; i<instances; ++i) {
        auto row = take(text);
        const auto layer = take(row, ' ');
        DecalInstance instance{};
        if (layer == "B") instance.background = true;
        else if (layer == "F") instance.background = false;
        else throw std::invalid_argument("Invalid decal layer");
        if (instance.background && foreground) throw std::invalid_argument("Decal instances are not in BG-then-FG order");
        if (!instance.background) foreground = true;
        instance.source_index = integer(take(row, ' '));
        instance.x = integer(take(row, ' ')); instance.y = integer(take(row, ' '));
        instance.scale_x = integer(take(row, ' ')); instance.scale_y = integer(take(row, ' '));
        instance.texture = integer(row);
        const int limit = instance.background ? 20 : 2;
        if (instance.source_index < 0 || instance.source_index >= limit || instance.texture < 0 ||
            instance.texture >= result.texture_count || (instance.scale_x != 1 && instance.scale_x != -1) ||
            (instance.scale_y != 1 && instance.scale_y != -1) || instance.x < -1'000'000 || instance.x > 1'000'000 ||
            instance.y < -1'000'000 || instance.y > 1'000'000)
            throw std::invalid_argument("Invalid decal instance transform/index");
        auto& seen = instance.background ? seen_background : seen_foreground;
        if (seen[instance.source_index]) throw std::invalid_argument("Duplicate decal source instance");
        seen[instance.source_index] = true;
        result.instances.push_back(instance);
    }
    if (!std::all_of(seen_background.begin(), seen_background.begin()+20, [](bool value) { return value; }) ||
        !std::all_of(seen_foreground.begin(), seen_foreground.begin()+2, [](bool value) { return value; }))
        throw std::invalid_argument("Static decal source index coverage changed");
    const int omitted = integer(take(text));
    if (omitted != 7) throw std::invalid_argument("Expected seven explicitly omitted Banner decals");
    const std::array<OmittedDecal,7> expected{{
        {true,20,"1-forsakencity/ragsB"}, {true,21,"1-forsakencity/rags"},
        {true,22,"1-forsakencity/ragsB"}, {true,23,"1-forsakencity/rags"},
        {true,24,"1-forsakencity/ragsB"}, {false,2,"generic/grass_a"}, {false,3,"generic/grass_d"}}};
    for (int i=0; i<omitted; ++i) {
        auto row = take(text);
        const auto layer = take(row, ' ');
        OmittedDecal entry{};
        if (layer == "B") entry.background = true;
        else if (layer == "F") entry.background = false;
        else throw std::invalid_argument("Invalid omitted decal layer");
        entry.source_index = integer(take(row, ' '));
        entry.name = std::string(row);
        if (!valid_name(entry.name) || entry.source_index < 0) throw std::invalid_argument("Invalid omitted decal");
        result.omitted.push_back(entry);
    }
    if (!text.empty()) throw std::invalid_argument("Trailing decal data");
    for (int i=0; i<omitted; ++i)
        if (result.omitted[i].background != expected[i].background || result.omitted[i].source_index != expected[i].source_index ||
            result.omitted[i].name != expected[i].name)
            throw std::invalid_argument("Animated Banner omission set changed");
    return result;
}
std::vector<draw_order::AuthoredDecalOwners> parse_authored_decals(
    std::string_view text,std::uint32_t expected_checksum,const RoomCatalog& catalog) {
    integrity(text,65'536,expected_checksum);
    header(text,"CDO1");
    if(take(text)!="81d04a56cb9b5cb981f3c7823388bed6082db2d5755d364c15c35bbcaf8b7746" ||
       take(text)!="6000000000000000" || integer(take(text))!=2 || catalog.definitions().size()!=2)
        throw std::invalid_argument("Invalid authored decal provenance/namespace/room count");
    std::vector<draw_order::AuthoredDecalOwners> result;
    for(std::size_t index=0;index<catalog.definitions().size();++index) {
        const auto& room=catalog.definitions()[index];
        auto row=take(text);
        if(take(row,' ')!="R" || take(row,' ')!=room.name)
            throw std::invalid_argument("Unknown, duplicate or reordered authored decal room");
        const int x=integer(take(row,' ')),y=integer(take(row,' '));
        const int width=integer(take(row,' ')),height=integer(take(row,' ')),raw_height=integer(take(row,' '));
        const int background=integer(take(row,' ')),foreground=integer(row);
        if(x!=room.bounds.x || y!=room.bounds.y || width!=room.bounds.width || height!=room.bounds.height ||
           raw_height<=0 || raw_height>1'000'000 || height!=(raw_height==184?180:raw_height) ||
           background<0 || background>64 || foreground<0 || foreground>64)
            throw std::invalid_argument("Invalid authored decal room bounds/counts");
        draw_order::AuthoredDecalOwners authored{&room,{},background,foreground};
        for(const bool back:{true,false}) {
            const int count=back?background:foreground;
            for(int ordinal=0;ordinal<count;++ordinal) {
                row=take(text);
                if(take(row,' ')!=(back?"B":"F") || integer(take(row,' '))!=ordinal)
                    throw std::invalid_argument("Invalid authored decal layer/ordinal coverage");
                const auto texture=take(row,' ');
                auto name=texture;
                if(name.size()>4 && name.substr(name.size()-4)==".png") name.remove_suffix(4);
                if(name.empty() || name.size()>192 || name.front()=='/' || name.front()=='\\' ||
                   name.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/\\-")!=std::string_view::npos)
                    throw std::invalid_argument("Invalid original decal texture key");
                const int px=integer(take(row,' ')),py=integer(take(row,' '));
                const int sx=integer(take(row,' ')),sy=integer(take(row,' ')),banner=integer(row);
                if(px < -1'000'000 || px>1'000'000 || py < -1'000'000 || py>1'000'000 ||
                   (sx!=1 && sx!=-1) || (sy!=1 && sy!=-1) || (banner!=0 && banner!=1))
                    throw std::invalid_argument("Invalid authored decal transform/classification");
                const auto identity=0x6000'0000'0000'0000ull | (std::uint64_t(index+1)<<32) |
                    (std::uint64_t(back?1:2)<<24) | std::uint64_t(ordinal+1);
                authored.owners.push_back({draw_order::OwnerKind::decal,identity,ordinal,&room,
                    back?9000:-10500,unsigned(ordinal),true,false,banner!=0,std::string(texture),
                    {float(px),float(py)},{float(sx),float(sy)}});
            }
        }
        result.push_back(std::move(authored));
    }
    if(!text.empty()) throw std::invalid_argument("Trailing authored decal metadata");
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
    const int animation_count=integer(take(text));
    if(animation_count!=24 && animation_count!=27) throw std::invalid_argument("Expected bounded legacy or death-animation closure");
    for(int i=0;i<animation_count;++i) {
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
