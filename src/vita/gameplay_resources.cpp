#include "gameplay_resources.hpp"
#include "material_table.hpp"
#include <set>
#include <sstream>
#include <stdexcept>

namespace celeste::diagnostic {
namespace {
const std::set<std::string> metadata_names{"global.mask","hazards.txt","player.txt","rooms.txt","owners.txt",
    "decals-catalog.txt","terrain.txt","spikes-catalog.txt","jumpthru.txt","strawberries.txt","spring.txt",
    "dust.txt","player-original.txt","materials.txt"};
std::vector<LogicalPlayerFrame> player_mapping(const std::string& text,const PlayerFrameBank& bank) {
    std::istringstream stream(text);
    return read_player_draw_mapping(stream,bank);
}
std::vector<gameplay_bridge::PagePixels> page_pixels(const std::map<std::string,std::string>& files,
                                                   const command_preflight::MaterialTable& table) {
    const auto ready=gameplay_bridge::prepare(0,table,{});
    if(ready.required_rgba_bytes()>512*1024) throw std::invalid_argument("Gameplay packed RGBA exceeds the existing 512 KiB bounded upload profile");
    std::set<std::string> expected=metadata_names;
    std::vector<gameplay_bridge::PagePixels> result;
    for(const auto& page:table.pages) {
        if(page.width>128 || page.height>128) throw std::invalid_argument("Gameplay packed page exceeds bounded 128x128 dimensions");
        const auto name="page"+std::to_string(page.id)+".rgba";
        expected.insert(name);
        const auto found=files.find(name);
        if(found==files.end()) throw std::invalid_argument("Missing gameplay material page: "+name);
        const auto& pixels=found->second;
        if(pixels.size()!=std::size_t(page.width)*std::size_t(page.height)*4)
            throw std::invalid_argument("Gameplay RGBA dimensions/byte count disagree: "+name);
        result.push_back({page,pixels});
    }
    std::set<std::string> actual;
    for(const auto& file:files) actual.insert(file.first);
    if(actual!=expected) throw std::invalid_argument("Gameplay file inventory differs from complete material page catalog");
    return result;
}
}
GameplayResources::Files GameplayResources::read_files(const std::vector<GameplayFilePin>& pins,const GameplayReader& read) {
    if(!read || pins.size()<metadata_names.size() || pins.size()>128)
        throw std::invalid_argument("Invalid gameplay reader or bounded file pin count");
    std::set<std::string> names;
    for(const auto& pin:pins) {
        if(pin.name.empty() || pin.name.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789.-")!=std::string::npos ||
           !pin.bytes || pin.bytes>32'000'000 || !names.insert(pin.name).second)
            throw std::invalid_argument("Invalid or duplicate gameplay file pin: "+pin.name);
    }
    for(const auto& name:metadata_names) if(!names.count(name)) throw std::invalid_argument("Missing gameplay file pin: "+name);
    Files files;
    for(const auto& pin:pins) {
        std::string bytes;
        try { bytes=read(pin.name,pin.bytes); }
        catch(const std::exception& error) { throw std::runtime_error("Gameplay resource "+pin.name+": "+error.what()); }
        if(bytes.size()!=pin.bytes || checksum(bytes)!=pin.checksum)
            throw std::invalid_argument("Gameplay file integrity mismatch: "+pin.name);
        files.emplace(pin.name,std::move(bytes));
    }
    return files;
}
GameplayResources::GameplayResources(const std::vector<GameplayFilePin>& pins,const GameplayReader& read)
    :GameplayResources(read_files(pins,read)) {}
GameplayResources::GameplayResources(Files files)
    :room(parse_mask(files.at("global.mask"),checksum(files.at("global.mask"))),
          parse_spikes(files.at("hazards.txt"),checksum(files.at("hazards.txt")))),
     player(parse_player_assets(files.at("player.txt"),checksum(files.at("player.txt")))),
     catalog(parse_room_catalog(files.at("rooms.txt"))),
     authored(parse_authored_decals(files.at("owners.txt"),checksum(files.at("owners.txt")),catalog)),
     decals(parse_static_decal_catalog(files.at("decals-catalog.txt"),checksum(files.at("decals-catalog.txt")),authored,true)),
     terrain(terrain::parse(files.at("terrain.txt"),checksum(files.at("terrain.txt")))),
     spikes(spike_commands::parse(files.at("spikes-catalog.txt"),checksum(files.at("spikes-catalog.txt")))),
     jumpthrus(jumpthru_commands::parse(files.at("jumpthru.txt"),checksum(files.at("jumpthru.txt")))),
     strawberries(strawberry_commands::parse(files.at("strawberries.txt"),checksum(files.at("strawberries.txt")))),
     springs(spring_commands::parse(files.at("spring.txt"),checksum(files.at("spring.txt")))),
     particles(particle_commands::parse(files.at("dust.txt"),checksum(files.at("dust.txt")))),
     mapping(player_mapping(files.at("player-original.txt"),player.bank)),
     materials(material_table::parse(files.at("materials.txt"),checksum(files.at("materials.txt")))),
     pixels(page_pixels(files,materials)) {
    for(const auto& logical:mapping) {
        bool found=false;
        for(const auto& sheet:terrain.sheets()) if(sheet.name==logical.sheet && sheet.width==logical.sheet_width && sheet.height==logical.sheet_height) found=true;
        if(!found) throw std::invalid_argument("Player original sheet dimensions disagree with gameplay terrain catalog: "+logical.name);
    }
}
gameplay_commands::Schedule GameplayResources::schedule(Session& session) const {
    auto* lifecycle=session.lifecycle();
    if(!lifecycle) throw std::invalid_argument("Gameplay production requires an automatic lifecycle");
    const std::string phase=lifecycle->phase();
    if(phase!="live" && phase!="respawn14") throw std::runtime_error("Unsupported gameplay lifecycle phase before Draw: "+phase);
    if(lifecycle->room_definition()!=&catalog.first() && lifecycle->room_definition()!=&catalog.definitions().at(1))
        throw std::invalid_argument("Gameplay session does not borrow this resource catalog");
    const auto frame=gameplay_projection::project(*lifecycle,catalog.first(),authored,
        {&decals,&terrain,true,&spikes,&jumpthrus,&strawberries,&springs,&particles});
    const auto cached=lifecycle->draw();
    return gameplay_projection::assemble(*lifecycle,frame,terrain,player.bank,mapping,cached);
}
command_preflight::ReadyFrame GameplayResources::prepare(unsigned frame,Session& session) const {
    try { return gameplay_bridge::prepare(frame,materials,gameplay_bridge::inputs(schedule(session))); }
    catch(const std::exception& error) { throw std::runtime_error("Gameplay production frame="+std::to_string(frame)+": "+error.what()); }
}
}
