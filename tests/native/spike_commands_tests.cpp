#include "asset_text.hpp"
#include "draw_order.hpp"
#include "spike_commands.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using namespace celeste;
using namespace celeste::spike_commands;
namespace {
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }

std::string pin(char digit) { return std::string(64,digit); }

std::string frame_row(const char* direction,const char* sheet,int x,int y,int width,int height,
                      int offset_x,int offset_y,int frame_width,int frame_height,const char* texture) {
    return std::string(direction)+' '+sheet+' '+std::to_string(x)+' '+std::to_string(y)+' '+
        std::to_string(width)+' '+std::to_string(height)+' '+std::to_string(offset_x)+' '+
        std::to_string(offset_y)+' '+std::to_string(frame_width)+' '+std::to_string(frame_height)+' '+
        texture+'\n';
}
std::string catalog_text() {
    return "CSPK1\n"+pin('a')+'\n'+pin('b')+'\n'+pin('c')+"\n2\n"+
        frame_row("up","Gameplay0",10,20,7,6,1,-2,8,9,"synthetic/up")+
        frame_row("left","Gameplay0",30,40,6,7,-1,2,9,8,"synthetic/left");
}
Catalog catalog() {
    auto text=catalog_text();
    return parse(text,asset_text::checksum(text));
}
std::string replace_once(std::string text,const std::string& old,const std::string& value) {
    const auto at=text.find(old);
    require(at!=std::string::npos,"Mutation target stands absent");
    text.replace(at,old.size(),value);
    return text;
}

RoomDefinition first_room() {
    return {"1",{0,0,320,180},49,{19,144},{
        {RoomObjectKind::spike_up,7,{40,168},16},
        {RoomObjectKind::spike_left,11,{272,80},16}}};
}
RoomDefinition second_room() {
    return {"2",{240,-184,320,180},50,{264,-24},{
        {RoomObjectKind::spike_up,8,{400,-72},16},
        {RoomObjectKind::spike_up,9,{432,-24},8}}};
}
struct Fixture {
    Body floor{{320,-40},Hitbox{100,8,{}},true};
    StaticWorld collision{{&floor},{}};
    RoomDefinition room1=first_room(),room2=second_room();
    std::unique_ptr<RoomRuntime> first,second;
    PlayerWorld world;
    Player player{world};
    Fixture() {
        first=std::make_unique<RoomRuntime>(room1,collision,true);
        second=std::make_unique<RoomRuntime>(room2,collision);
    }
    draw_order::RosterSnapshot snapshot(bool both) {
        draw_order::RosterSnapshot state;
        state.initial_room=&room1;
        for(const auto* room:{first.get(),second.get()}) {
            if(!both && room==second.get()) continue;
            for(const auto& entity:room->entities) state.roster.push_back({room,entity.get(),nullptr});
        }
        state.roster.push_back({nullptr,nullptr,&player});
        return state;
    }
    RoomEntity* spike(RoomRuntime& room,int authored_id) {
        for(const auto& entity:room.entities)
            if(entity->authored_id==authored_id && std::holds_alternative<StaticSpike>(entity->object)) return entity.get();
        throw std::runtime_error("Fixture spike is missing");
    }
};
std::vector<Command> project_fixture(Fixture& fixture,bool both,const Catalog& value) {
    auto state=fixture.snapshot(both);
    return project(draw_order::project(state,{}),state.roster,value);
}
void up_and_left_commands_use_actual_cells_positions_and_frame_descriptors() {
    Fixture fixture;
    const auto commands=project_fixture(fixture,false,catalog());
    require(commands.size()==4,"Two two-piece spikes must emit four commands");
    const auto& up=commands[0];
    require(up.identity==fixture.spike(*fixture.first,7)->object_identity && up.room=="1" && up.authored_id==7,
        "Up command must bind the live native entity authored identity");
    require(up.direction==SpikeDirection::up && up.piece==0,"Up command direction/piece changed");
    require(up.texture=="synthetic/up" && up.sheet=="Gameplay0","Up command atlas key/sheet changed");
    require(up.source_x==10 && up.source_y==20 && up.source_width==7 && up.source_height==6,
        "Up command source rectangle changed");
    require(up.position.x==44 && up.position.y==169,"Up world position must use entity position plus source image offset");
    require(up.origin.x==5 && up.origin.y==7,"Up origin must use frame justify minus draw offset");
    require(up.scale.x==1 && up.scale.y==1 && up.rotation==0 && up.effects=="None",
        "Up command transform/effects changed");
    require(up.color.r==255 && up.color.g==255 && up.color.b==255 && up.color.a==255,
        "Up command must use the enabled white source color");
    require(commands[1].piece==1 && commands[1].position.x==52 && commands[1].position.y==169,
        "Up pieces must advance by eight pixels in native component order");
    const auto& left=commands[2];
    require(left.authored_id==11 && left.direction==SpikeDirection::left && left.piece==0,
        "Left command identity/direction/piece changed");
    require(left.texture=="synthetic/left" && left.source_x==30 && left.source_y==40 &&
            left.source_width==6 && left.source_height==7,"Left command source rectangle changed");
    require(left.position.x==273 && left.position.y==84,"Left world position must use entity position plus source image offset");
    require(left.origin.x==8 && left.origin.y==6,"Left origin must use frame justify minus draw offset");
    require(commands[3].piece==1 && commands[3].position.x==273 && commands[3].position.y==92,
        "Left pieces must advance by eight pixels in native component order");
}
void outgoing_room_commands_precede_incoming_room_commands() {
    Fixture fixture;
    const auto commands=project_fixture(fixture,true,catalog());
    require(commands.size()==7,"Both rooms must emit their native spike pieces");
    std::vector<std::string> rooms;
    for(const auto& command:commands) rooms.push_back(command.room);
    const std::vector<std::string> expected{"1","1","1","1","2","2","2"};
    require(rooms==expected,"Outgoing spike commands must precede incoming spike commands");
}
void missing_family_rejects_before_publication() {
    Fixture fixture;
    auto value=catalog();
    value.frames[1].texture.clear();
    try { project_fixture(fixture,false,value); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A missing spike family descriptor must reject");
}
void incomplete_image_cells_reject() {
    Fixture fixture;
    fixture.spike(*fixture.first,7)->image_cells.pop_back();
    try { project_fixture(fixture,false,catalog()); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A spike with missing image cells must reject");
}
void extra_image_cells_reject() {
    Fixture fixture;
    fixture.spike(*fixture.first,7)->image_cells.emplace_back(0,0);
    try { project_fixture(fixture,false,catalog()); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A spike with extra image cells must reject");
}
void invalid_image_cell_rejects_parameterized() {
    Fixture fixture;
    for(const std::pair<int,int>& cell:std::vector<std::pair<int,int>>{{1,0},{0,1}}) {
        fixture.spike(*fixture.first,7)->image_cells[0]=cell;
        try { project_fixture(fixture,false,catalog()); }
        catch(const std::invalid_argument&) { continue; }
        throw std::runtime_error("An invalid spike image cell must reject");
    }
}
void missing_roster_entity_rejects() {
    Fixture fixture;
    auto state=fixture.snapshot(false);
    const auto drawn=draw_order::project(state,{});
    const auto identity=fixture.spike(*fixture.first,7)->object_identity;
    state.roster.erase(std::remove_if(state.roster.begin(),state.roster.end(),
        [&](const RoomRosterEntry& entry) { return entry.entity && entry.entity->object_identity==identity; }),state.roster.end());
    try { project(drawn,state.roster,catalog()); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A dispatched spike without a roster entity must reject");
}
void aliased_roster_entity_rejects() {
    Fixture fixture;
    auto state=fixture.snapshot(false);
    const auto drawn=draw_order::project(state,{});
    const auto identity=fixture.spike(*fixture.first,7)->object_identity;
    for(const auto& entry:state.roster) if(entry.entity && entry.entity->object_identity==identity) {
        state.roster.push_back(entry);
        break;
    }
    try { project(drawn,state.roster,catalog()); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("An aliased spike roster identity must reject");
}
void duplicate_dispatch_rejects() {
    Fixture fixture;
    auto state=fixture.snapshot(false);
    auto drawn=draw_order::project(state,{});
    require(!drawn.dispatch.empty(),"Fixture dispatch is empty");
    drawn.dispatch.push_back(drawn.dispatch.front());
    try { project(drawn,state.roster,catalog()); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A duplicate spike dispatch must reject");
}
void foreign_room_binding_rejects() {
    Fixture fixture;
    auto state=fixture.snapshot(false);
    auto drawn=draw_order::project(state,{});
    for(auto& owner:drawn.live) if(owner.kind==draw_order::OwnerKind::spikes && owner.room==&fixture.room1) owner.room=&fixture.room2;
    try { project(drawn,state.roster,catalog()); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("A foreign spike room binding must reject");
}
void catalog_accepts_pinned_shape() {
    const auto value=catalog();
    require(value.frames[0].texture=="synthetic/up" && value.frames[1].texture=="synthetic/left",
        "Catalog direction rows must bind their atlas keys");
    require(value.provenance[0]==pin('a') && value.provenance[1]==pin('b') && value.provenance[2]==pin('c'),
        "Catalog provenance pins changed");
}
void catalog_rejects_bad_versions_pins_checksums_and_shapes_parameterized() {
    const auto text=catalog_text();
    const std::vector<std::pair<std::string,std::string>> mutations{
        {"CSPK1","CSPK2"},{"CSPK1","CDSC1"},
        {std::string(pin('a')),std::string(63,'d')},
        {std::string(pin('b')),std::string(64,'A')},
        {"\n2\n","\n3\n"},{"\n2\n","\n1\n"},
        {"up Gameplay0","down Gameplay0"},
        {"left Gameplay0","right Gameplay0"},
        {"Gameplay0 10 20 7 6 1 -2 8 9 synthetic/up","Gameplay0 4096 20 7 6 1 -2 8 9 synthetic/up"},
        {"Gameplay0 10 20 7 6 1 -2 8 9 synthetic/up","Gameplay0 10 20 0 6 1 -2 8 9 synthetic/up"},
        {"Gameplay0 10 20 7 6 1 -2 8 9 synthetic/up","Gameplay0 10 20 7 6 1 -2 0 9 synthetic/up"},
        {"Gameplay0 10 20 7 6 1 -2 8 9 synthetic/up","Gameplay0 10 20 7 6 4097 -2 8 9 synthetic/up"},
        {"synthetic/up","synthetic/left"},
        {"synthetic/up","../up"}
    };
    for(const auto& mutation:mutations) {
        const auto changed=replace_once(text,mutation.first,mutation.second);
        try { parse(changed,asset_text::checksum(changed)); }
        catch(const std::invalid_argument&) { continue; }
        throw std::runtime_error("Malformed spike catalog was accepted: "+mutation.second);
    }
}
void catalog_rejects_wrong_integrity() {
    const auto text=catalog_text();
    try { parse(text,asset_text::checksum(text)^1u); }
    catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Wrong spike catalog integrity was accepted");
}
void catalog_rejects_truncation_and_trailing_data() {
    const auto text=catalog_text();
    const auto rejects=[&](const std::string& value) {
        try { parse(value,asset_text::checksum(value)); }
        catch(const std::invalid_argument&) { return true; }
        return false;
    };
    auto truncated=text;
    truncated.erase(truncated.find_last_of('\n'));
    require(rejects(truncated),"Truncated spike catalog was accepted");
    require(rejects(text+"extra\n"),"Trailing spike catalog data was accepted");
}
}

int main() {
    int passed=0;
    const std::vector<std::pair<const char*,void(*)()>> tests{
        {"up_and_left_commands_use_actual_cells_positions_and_frame_descriptors",up_and_left_commands_use_actual_cells_positions_and_frame_descriptors},
        {"outgoing_room_commands_precede_incoming_room_commands",outgoing_room_commands_precede_incoming_room_commands},
        {"missing_family_rejects_before_publication",missing_family_rejects_before_publication},
        {"incomplete_image_cells_reject",incomplete_image_cells_reject},
        {"extra_image_cells_reject",extra_image_cells_reject},
        {"invalid_image_cell_rejects_parameterized",invalid_image_cell_rejects_parameterized},
        {"missing_roster_entity_rejects",missing_roster_entity_rejects},
        {"aliased_roster_entity_rejects",aliased_roster_entity_rejects},
        {"duplicate_dispatch_rejects",duplicate_dispatch_rejects},
        {"foreign_room_binding_rejects",foreign_room_binding_rejects},
        {"catalog_accepts_pinned_shape",catalog_accepts_pinned_shape},
        {"catalog_rejects_bad_versions_pins_checksums_and_shapes_parameterized",catalog_rejects_bad_versions_pins_checksums_and_shapes_parameterized},
        {"catalog_rejects_wrong_integrity",catalog_rejects_wrong_integrity},
        {"catalog_rejects_truncation_and_trailing_data",catalog_rejects_truncation_and_trailing_data}
    };
    for(const auto& [name,test]:tests) {
        try { test(); ++passed; }
        catch(const std::exception& error) { std::cerr<<name<<": "<<error.what()<<'\n'; return 1; }
    }
    std::cout<<passed<<" spike command behaviors passed\n";
    return 0;
}
