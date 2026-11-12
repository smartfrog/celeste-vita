#include "asset_text.hpp"
#include "strawberry_commands.hpp"
#include <iostream>
#include <functional>
#include <stdexcept>

using namespace celeste;
using namespace celeste::strawberry_commands;
namespace {
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
void rejects(const std::function<void()>& operation) {
    try { operation(); } catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Invalid Strawberry input was accepted");
}
std::string catalog_text() {
    std::string text="CSTR1\n";
    for(char digit:{'a','b','c'}) text+=std::string(64,digit)+'\n';
    text+="idle 36\n";
    for(int index=0;index<36;++index) text+=std::to_string(index<28?index%7:index-28)+(index==35?"\n":" ");
    text+="8\n";
    for(int index=0;index<8;++index)
        text+=std::to_string(index)+" Synthetic "+std::to_string(index*20)+" 20 10 12 -4 -1 18 16 synthetic/frame"+std::to_string(index)+'\n';
    return text;
}
Catalog catalog() { const auto text=catalog_text(); return parse(text,asset_text::checksum(text)); }
struct Fixture {
    RoomDefinition definition{"test",{0,0,320,180},49,{19,144},{{RoomObjectKind::strawberry,11,{80,40},0}}};
    StaticWorld collision;
    RoomRuntime room{definition,collision};
    RoomEntity* entity=room.entities.back().get();
    RoomStrawberry& berry=std::get<RoomStrawberry>(entity->object);
    std::vector<RoomRosterEntry> roster{{&room,entity,nullptr}};
    draw_order::DrawProjection drawn;
    Fixture() {
        draw_order::DrawOwner owner;
        owner.kind=draw_order::OwnerKind::strawberry;
        owner.identity=entity->object_identity;owner.authored_id=11;owner.room=&definition;
        drawn.live.push_back(owner);drawn.dispatch.push_back(0);
    }
    std::vector<Command> commands() { return project(drawn,roster,catalog()); }
};
void projection_uses_native_animation_index_and_unrounded_local_y() {
    Fixture fixture;
    fixture.berry.sprite_frame=8;
    fixture.berry.light_y=0.125f;
    const auto commands=fixture.commands();
    require(commands.size()==1,"Expected one Sprite command");
    const auto& command=commands.front();
    require(command.identity==fixture.entity->object_identity && command.room=="test" && command.authored_id==11,"Actual owner binding changed");
    require(command.animation_frame==8 && command.texture_frame==1 && command.texture=="synthetic/frame1","Animation index must map through the source idle sequence");
    require(command.source_x==20 && command.source_y==20 && command.source_width==10 && command.source_height==12,"Source clip changed");
    require(command.position.x==80 && command.position.y==40.125f,"Sprite position must retain fractional local Y");
    require(command.origin.x==5 && command.origin.y==7,"Center origin must include atlas trim offset");
    require(command.scale.x==1 && command.scale.y==1 && command.rotation==0 && command.effects=="None","Idle does not spin");
    require(command.color.r==255 && command.color.g==255 && command.color.b==255 && command.color.a==255,"Idle is white");
}
void frozen_incoming_state_projects_initial_frame() {
    Fixture fixture;fixture.room.update(1.f/60,true);
    const auto command=fixture.commands().front();
    require(command.animation_frame==0 && command.position.y==40 && fixture.berry.updates==0,"Incoming Strawberry must remain frozen");
}
void source_visual_update_uses_single_advance_even_for_large_delta() {
    Fixture fixture;fixture.entity->update(0.25f);
    require(fixture.berry.sprite_frame==1 && fixture.berry.sprite_timer==0.15f,"Source Sprite advances once, not while catching up");
}
void projection_is_observational() {
    Fixture fixture;fixture.entity->update(1.f/60);
    const auto before=fixture.berry;
    const auto words=fixture.room.scoped_random.state_words();
    fixture.commands();fixture.commands();
    require(fixture.berry.sprite_frame==before.sprite_frame && fixture.berry.sprite_timer==before.sprite_timer && fixture.berry.wobble==before.wobble && fixture.berry.updates==before.updates,"Projection mutated visual state");
    require(fixture.room.scoped_random.state_words()==words && fixture.room.scoped_random.calls()==0,"Projection consumed RNG");
}
void owner_binding_negatives_parameterized() {
    for(int mutation=0;mutation<7;++mutation) {
        Fixture fixture;
        if(mutation==0) fixture.roster.clear();
        if(mutation==1) fixture.roster.push_back(fixture.roster.front());
        if(mutation==2) fixture.drawn.dispatch.push_back(0);
        if(mutation==3) fixture.drawn.live[0].authored_id=12;
        if(mutation==4) fixture.drawn.live[0].room=nullptr;
        if(mutation==5) fixture.drawn.live[0].identity+=100;
        if(mutation==6) fixture.drawn.dispatch[0]=1;
        rejects([&] { fixture.commands(); });
    }
}
void unsupported_pulse_frame_rejects() {
    Fixture fixture;fixture.berry.sprite_frame=35;
    rejects([&] { fixture.commands(); });
}
void invisible_owner_is_not_dispatched() {
    Fixture fixture;fixture.drawn.live[0].visible=false;fixture.drawn.dispatch.clear();
    require(fixture.commands().empty(),"Undispatched Strawberry must not emit");
}
void duplicate_draw_owner_identity_rejects() {
    Fixture fixture;fixture.drawn.live.push_back(fixture.drawn.live.front());fixture.drawn.dispatch.push_back(1);
    rejects([&] { fixture.commands(); });
}
void fresh_runtime_binds_fresh_observable_entity_identity() {
    Fixture first,second;
    require(first.commands().front().identity!=second.commands().front().identity,"Fresh native entity instances must not alias");
}
void catalog_shape_negatives_parameterized() {
    const auto original=catalog_text();
    for(const auto& mutation:std::vector<std::pair<std::string,std::string>>{
        {"CSTR1","CSTR2"},{"idle 36","flap 36"},{"idle 36","idle 35"},
        {"\n8\n","\n7\n"},{"0 1 2 3","0 8 2 3"},
        {"0 Synthetic","1 Synthetic"},{"synthetic/frame1","synthetic/frame0"},
        {" 10 12 -4 -1"," 0 12 -4 -1"},{" 18 16 "," 0 16 "},
        {" -4 -1 "," -4097 -1 "},{"synthetic/frame0","../frame0"},
        {std::string(64,'a'),std::string(64,'A')}}) {
        auto changed=original;const auto at=changed.find(mutation.first);
        require(at!=std::string::npos,"Missing catalog mutation precondition");
        changed.replace(at,mutation.first.size(),mutation.second);
        rejects([&] { parse(changed,asset_text::checksum(changed)); });
    }
}
void catalog_trailing_rejects() { const auto text=catalog_text()+"extra\n";rejects([&] { parse(text,asset_text::checksum(text)); }); }
void catalog_truncation_rejects() { auto text=catalog_text();text.pop_back();rejects([&] { parse(text,asset_text::checksum(text)); }); }
void catalog_integrity_rejects() { const auto text=catalog_text();rejects([&] { parse(text,asset_text::checksum(text)^1); }); }
}
int main() {
    int count=0;
    for(const auto test:{projection_uses_native_animation_index_and_unrounded_local_y,frozen_incoming_state_projects_initial_frame,
        source_visual_update_uses_single_advance_even_for_large_delta,projection_is_observational,owner_binding_negatives_parameterized,
        unsupported_pulse_frame_rejects,invisible_owner_is_not_dispatched,duplicate_draw_owner_identity_rejects,
        fresh_runtime_binds_fresh_observable_entity_identity,catalog_shape_negatives_parameterized,
        catalog_trailing_rejects,catalog_truncation_rejects,catalog_integrity_rejects}) {
        try { test();++count; } catch(const std::exception& error) { std::cerr<<"behavior "<<count<<": "<<error.what()<<'\n';return 1; }
    }
    std::cout<<count<<" Strawberry behaviors passed\n";
}
