#include "gameplay_resources.hpp"
#include "session_profile.hpp"
#include "gameplay_commands_trace.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <type_traits>

using namespace celeste;
using namespace celeste::diagnostic;
namespace {
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
void incomplete_pins_reject_without_io() {
    unsigned reads=0;
    try { GameplayResources resources({},[&](const auto&,auto) { ++reads;return std::string{}; }); }
    catch(const std::invalid_argument&) { require(reads==0,"Missing pins must reject before IO");return; }
    throw std::runtime_error("Incomplete resource pins must reject");
}
void actual_route(const char* inventory,const char* route,bool trace,bool accept_semantic) {
    std::ifstream index(inventory);
    require(bool(index),"Cannot read in-place resource inventory");
    std::vector<GameplayFilePin> pins;std::map<std::string,std::string> paths;
    std::string name,path;std::size_t bytes;std::uint32_t hash;
    while(index>>name>>path>>bytes>>hash) { pins.push_back({name,bytes,hash});require(paths.emplace(name,path).second,"Duplicate input inventory key"); }
    require(index.eof(),"Malformed in-place resource inventory");
    GameplayResources resources(pins,[&](const auto& file,auto limit) { return read_asset(paths.at(file).c_str(),limit); });
    require(resources.materials.bindings.size()==274 && resources.pixels.size()==16,"Real complete bounded resource closure required");
    auto session=make_session(resources.room.world,&resources.player.bank,&resources.catalog,&resources.authored);
    bool startup_blocked=false;
    try { resources.prepare(0,session); }
    catch(const std::runtime_error& error) {
        startup_blocked=std::string(error.what()).find("Gameplay preflight frame=0")!=std::string::npos;
    }
    require(startup_blocked,"Actual production startup must honestly fail before graphics initialization");
    const auto* first=&resources.catalog.first();
    for(unsigned reset=0;reset<2;++reset) {
        session.step({{},true,false});
        require(session.lifecycle()->room_definition()==first,"Reset must retain unmoved resource definitions");
        for(const auto& owner:resources.authored) for(const auto& decal:owner.owners)
            require(decal.room==owner.room,"Authored owner room pointers must remain stable through resets");
    }
    Session playback(resources.room.world,resources.player.bank,false,1,&resources.catalog,&resources.authored);
    FirstRoomSession expected(resources.room.world,resources.player.bank,false,1,&resources.catalog,&resources.authored);
    const command_preflight::Policy accept_zero_area{
        command_preflight::Policy::ZeroAreaBanner::accept_semantic_no_raster};
    std::ifstream controls(route);require(bool(controls),"Cannot read existing legal controls");
    Controller controller;unsigned count=0,blocked=0,invalid=0,command_count=0,first_calls=0,second_calls=0;int tick,x,y,jump,dash,grab;
    std::size_t geometry_words=0,nan_words=0,raster_total=0,semantic_total=0;
    std::map<unsigned,unsigned> frame_semantic_counts;
    constexpr std::int32_t source_nan_bits=std::int32_t(0xFFC00000u);
    while(controls>>tick>>x>>y>>jump>>dash>>grab) {
        require(tick==int(count) && count<3600,"Invalid route sequence");
        Controls raw;raw.left=x<0;raw.right=x>0;raw.up=y<0;raw.down=y>0;raw.cross=jump;raw.square=dash;raw.l=grab;
        const auto sample=controller.sample(raw);
        playback.step(sample);expected.step(1.f/60,sample.player);
        const auto before=playback.lifecycle()->random().calls();
        const auto schedule=resources.schedule(playback);
        for(const auto& entry:playback.lifecycle()->room_roster()) if(entry.room) {
            auto& calls=entry.room->definition.name=="1" ? first_calls : second_calls;
            calls=entry.room->scoped_random.calls();
        }
        const auto expected_draw=expected.draw();
        require(playback.lifecycle()->random().calls()==before,"Projection and cached Draw must not consume RNG");
        for(unsigned node=0;node<4;++node) {
            const auto actual=playback.presentation()->pose().hair_nodes[node],other=expected.presentation().pose().hair_nodes[node];
            require(actual.x==other.x && actual.y==other.y,"Production must use exactly one Draw, without additional floor/normalization");
        }
        require(!expected_draw.empty(),"Reference must exercise its single actual Draw");
        require(playback.lifecycle()->camera().x==expected.camera().x && playback.lifecycle()->camera().y==expected.camera().y,
            "Production projection must preserve Source camera");
        require(playback.lifecycle()->random().state_words()==expected.random().state_words(),"Projection must preserve global RNG state");
        const auto input=gameplay_bridge::inputs(schedule);
        require(input.size()==schedule.commands().size(),"Every schedule command must reach preflight unchanged");
        unsigned frame_semantic=0,frame_raster=0;
        for(std::size_t i=0;i<input.size();++i) {
            require(input[i].geometry.vertices==schedule.commands()[i].geometry.vertices,"Geometry bit words must not be recomputed or sanitized");
            geometry_words+=input[i].geometry.vertices.size()*input[i].geometry.vertices[0].size();
            for(const auto& vertex:input[i].geometry.vertices)
                for(const auto word:vertex) if(word==source_nan_bits) ++nan_words;
            if(input[i].command.source_width==0 || input[i].command.source_height==0 || !input[i].geometry.finite) ++invalid;
            if(input[i].coverage==command_preflight::Coverage::semantic_zero_area_banner) ++frame_semantic;
            else ++frame_raster;
        }
        if(accept_semantic) {
            const auto ready=gameplay_bridge::prepare(count,resources.materials,input,accept_zero_area);
            require(ready.commands().size()==input.size(),"Opt-in must retain the full ordered CPU command set");
            require(frame_semantic+frame_raster==ready.commands().size(),"Coverage counts must sum the full frame");
            ++frame_semantic_counts[frame_semantic];
            std::vector<command_submission::UploadedPage> pages;
            for(const auto& page:ready.pages())
                pages.push_back({page.id,page.width,page.height,unsigned(pages.size()+1)});
            std::vector<unsigned> events;
            unsigned begins=0,quads=0,ends=0,acks=0;
            command_submission::submit(ready,pages,{playback.lifecycle()->camera(),960,544},
                {[&](const auto&) { ++begins;events.push_back(0); },
                 [&](auto,const auto&) { ++quads;events.push_back(1); },
                 [&] { ++ends;events.push_back(2); },
                 [&](const auto& command) {
                     ++acks;events.push_back(3);
                     require(command.coverage==command_preflight::Coverage::semantic_zero_area_banner,
                         "Ack must carry semantic coverage rather than a raster claim");
                 }});
            std::vector<unsigned> expected_events;
            if(frame_raster) expected_events.push_back(0);
            for(const auto& command:ready.commands()) expected_events.push_back(
                command.coverage==command_preflight::Coverage::semantic_zero_area_banner ? 3u : 1u);
            if(frame_raster) expected_events.push_back(2);
            require(events==expected_events && quads==frame_raster && acks==frame_semantic,
                "Full route sink must emit one ordered ack per semantic and quads only for raster");
            require(begins==(frame_raster?1u:0u) && ends==(frame_raster?1u:0u),
                "Ack-only route frames must not start or end a raster batch");
            semantic_total+=frame_semantic;raster_total+=frame_raster;
        } else {
            unsigned callbacks=0;
            try {
                gameplay_bridge::submit(count,resources.materials,input,{}, {playback.lifecycle()->camera(),960,544},
                    {[&](const auto&) { ++callbacks; },[&](auto,const auto&) { ++callbacks; },[&] { ++callbacks; },
                     [&](const auto&) { ++callbacks; }});
            } catch(const std::runtime_error& error) {
                require(std::string(error.what()).find("Gameplay preflight frame=")!=std::string::npos,"Must fail at preflight, not page lookup/submission");
                ++blocked;
            }
            require(callbacks==0,"Every invalid actual route frame must stop before sink callbacks");
        }
        if(trace) native_test::write_gameplay_schedule(std::cout,count,schedule);
        command_count+=input.size();++count;
    }
    require(controls.eof() && count==514 && invalid==5929,"The full route must retain all known invalid commands");
    require(command_count==680226 && !playback.lifecycle()->transition(),"Actual retained-room route must assemble its complete command stream");
    require(first_calls==19 && second_calls==15 && playback.lifecycle()->random().calls()==946,"Production Draw must retain accepted scoped 19/15 and global 946 RNG calls");
    require(geometry_words==13604520 && nan_words==47432,"CPU XYZUV word count and source NaN bits must remain unchanged");
    if(accept_semantic) {
        require(blocked==0 && semantic_total==5929 && raster_total==674297,"Opt-in must accept all 514 frames with exact raster/semantic split");
        require(frame_semantic_counts.size()==3 && frame_semantic_counts[13]==374 && frame_semantic_counts[17]==39 &&
                frame_semantic_counts[4]==101,"Per-frame semantic strip counts must match the pinned Source route");
        if(!trace) std::cout<<"514 production route frames; 680226 commands; 5929 ordered semantic acks; 674297 raster quads; 13604520 CPU words; 47432 NaN bits; zero unintended callbacks\n";
    } else {
        require(blocked==514,"Default policy must keep all 514 whole-frame failures");
        if(!trace) std::cout<<"514 production route frames; 680226 commands; 5929 invalid commands; 514 strict failures; zero sink callbacks\n";
    }
}
}
int main(int argc,char** argv) {
    static_assert(!std::is_move_constructible_v<GameplayResources> && !std::is_copy_constructible_v<GameplayResources>);
    try {
        if(argc==3) { actual_route(argv[1],argv[2],false,false);return 0; }
        if(argc==4) {
            const std::string mode=argv[3];
            if(mode=="trace") { actual_route(argv[1],argv[2],true,false);return 0; }
            if(mode=="semantic-on") { actual_route(argv[1],argv[2],false,true);return 0; }
            throw std::invalid_argument("Expected trace or semantic-on route mode");
        }
        if(argc==5) {
            require(std::string(argv[3])=="trace" && std::string(argv[4])=="semantic-on",
                "Expected trace semantic-on route mode");
            actual_route(argv[1],argv[2],true,true);return 0;
        }
        require(argc==1,"Expected optional in-place inventory and controls");
        incomplete_pins_reject_without_io();
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
