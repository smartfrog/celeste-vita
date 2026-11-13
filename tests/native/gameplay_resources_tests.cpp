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
void actual_route(const char* inventory,const char* route,bool trace) {
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
    std::ifstream controls(route);require(bool(controls),"Cannot read existing legal controls");
    Controller controller;unsigned count=0,blocked=0,invalid=0,command_count=0,first_calls=0,second_calls=0;int tick,x,y,jump,dash,grab;
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
        for(std::size_t i=0;i<input.size();++i) {
            require(input[i].geometry.vertices==schedule.commands()[i].geometry.vertices,"Geometry bit words must not be recomputed or sanitized");
            if(input[i].command.source_width==0 || input[i].command.source_height==0 || !input[i].geometry.finite) ++invalid;
        }
        unsigned callbacks=0;
        try {
            gameplay_bridge::submit(count,resources.materials,input,{}, {playback.lifecycle()->camera(),960,544},
                {[&](const auto&) { ++callbacks; },[&](auto,const auto&) { ++callbacks; },[&] { ++callbacks; }});
        } catch(const std::runtime_error& error) {
            require(std::string(error.what()).find("Gameplay preflight frame=")!=std::string::npos,"Must fail at preflight, not page lookup/submission");
            ++blocked;
        }
        require(callbacks==0,"Every invalid actual route frame must stop before sink callbacks");
        if(trace) native_test::write_gameplay_schedule(std::cout,count,schedule);
        command_count+=input.size();++count;
    }
    require(controls.eof() && count==514 && blocked==514 && invalid==5929,"The full route must retain all known invalid commands and frame failures");
    require(command_count==680226 && !playback.lifecycle()->transition(),"Actual retained-room route must assemble its complete command stream");
    require(first_calls==19 && second_calls==15 && playback.lifecycle()->random().calls()==946,"Production Draw must retain accepted scoped 19/15 and global 946 RNG calls");
    if(!trace) std::cout<<"514 production route frames; 680226 commands; 5929 invalid commands; 514 strict failures; zero sink callbacks\n";
}
}
int main(int argc,char** argv) {
    static_assert(!std::is_move_constructible_v<GameplayResources> && !std::is_copy_constructible_v<GameplayResources>);
    try {
        if(argc==3 || argc==4) { actual_route(argv[1],argv[2],argc==4);return 0; }
        require(argc==1,"Expected optional in-place inventory and controls");
        incomplete_pins_reject_without_io();
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
