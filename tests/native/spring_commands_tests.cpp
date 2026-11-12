#include "spring_commands.hpp"
#include "asset_text.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace celeste;
namespace {
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
template<class F> void rejects(F operation) {
    try { operation(); } catch(const std::logic_error&) { return; }
    throw std::runtime_error("Invalid Spring contract must reject");
}
struct Fixture {
    RoomDefinition definition{"fixture",{-128,-184,320,180},50,{-64,-32},{
        {RoomObjectKind::spring,7,{-40.25f,-32}},
        {RoomObjectKind::spring,8,{24,-32}}}};
    Body support{{-128,-32},Hitbox{256,8,{}},true};
    StaticWorld collision{{&support},{}};
    RoomRuntime room{definition,collision};
    spring_commands::Catalog catalog{{"FixtureSheet",32,48,6,4,-3,-10,18,20,"fixture/idle"},"fixture/idle"};
    draw_order::DrawProjection drawn;
    std::vector<const RoomRuntime*> rooms{&room};
    Fixture() {
        for(unsigned i=1;i<room.entities.size();++i) drawn.live.push_back({draw_order::OwnerKind::spring,
            room.entities[i]->object_identity,room.entities[i]->authored_id,&definition,-8501,i,true,false,false});
        drawn.dispatch={1,0};
    }
    RoomSpring& spring() { return std::get<RoomSpring>(room.entities[1]->object); }
    std::vector<spring_commands::Command> project() const { return spring_commands::project(drawn,catalog,rooms); }
};
void ordered_outline_and_main_bind_actual_native_owners() {
    Fixture f;const auto commands=f.project();require(commands.size()==18,"Every Spring emits eight outlines then its main image");
    const Vec2 offsets[]={{-1,-1},{-1,0},{-1,1},{0,-1},{0,1},{1,-1},{1,0},{1,1},{0,0}};
    for(unsigned i=0;i<commands.size();++i) {
        const auto& command=commands[i];const auto& image=command.image;
        const unsigned dispatch=i/9,piece=i%9;const auto& entity=*f.room.entities[dispatch==0?2:1];
        require(command.authored_id==entity.authored_id && command.piece==piece && command.dispatch_index==dispatch &&
            image.identity==entity.object_identity && image.room=="fixture","Semantic id, real native identity, dispatch and piece must agree");
        require(image.position.x==entity.position().x+offsets[piece].x && image.position.y==entity.position().y+offsets[piece].y,
            "Outline order is x outer, y inner, skipping center; main follows");
        require(image.color.r==(piece==8?255:0) && image.color.g==image.color.r && image.color.b==image.color.r && image.color.a==255,
            "Outline is opaque black, main is restored opaque white");
        require(image.sheet=="FixtureSheet" && image.texture=="fixture/idle" && image.source_x==32 && image.source_y==48 &&
            image.source_width==6 && image.source_height==4 && image.origin.x==6 && image.origin.y==10 &&
            image.scale.x==1 && image.scale.y==1 && image.rotation==0 && image.effects=="None" &&
            image.ordinal==-1 && image.slice==-1 && !image.background,"Logical dimensions, trim sign and default Image fields must be exact");
    }
}
void trim_and_untrimmed_origin_matrix_parameterized() {
    for(const Vec2 trim:{Vec2{0,0},Vec2{-3,-10},Vec2{-12,-16}}) {
        Fixture f;f.catalog.idle.offset_x=trim.x;f.catalog.idle.offset_y=trim.y;
        const auto commands=f.project();const auto& image=commands.back().image;
        require(image.origin.x==9+trim.x && image.origin.y==20+trim.y && image.position.x==-40.25f && image.position.y==-32,
            "Trim changes submitted origin only, including negative origins");
    }
}
std::int32_t bits(float value) { std::int32_t result;std::memcpy(&result,&value,sizeof(value));return result; }
void shared_geometry_uses_actual_negative_world_arithmetic() {
    Fixture f;const auto image=f.project().back().image;const auto geometry=decal_commands::project_geometry(image,128,128);
    const Vec2 xy[]={{-46.25f,-42},{-40.25f,-42},{-46.25f,-38},{-40.25f,-38}};
    for(unsigned i=0;i<4;++i) {
        const std::array<std::int32_t,5> expected{{bits(xy[i].x),bits(xy[i].y),bits(0),bits((i%2?38.f:32.f)/128),bits((i/2?52.f:48.f)/128)}};
        require(geometry.vertices[i]==expected && geometry.finite,"Shared geometry must retain exact XYZUV component bits");
    }
}
void projection_does_not_mutate_native_state_or_random() {
    Fixture f;const auto rng=f.room.scoped_random.state_words();const auto events=f.room.random_events;
    const auto before=f.project();
    for(unsigned i=0;i<5;++i) f.project();
    require(f.spring().updates==0 && f.spring().wiggler==0 && f.spring().body.position.x==-40.25f &&
        f.spring().attached==&f.support && f.room.scoped_random.state_words()==rng && f.room.random_events==events,
        "Sampling must not update, wiggle, move, reattach or consume random");
    f.room.update(1.f/60,false);f.room.update(1.f/60,true);
    const auto after=f.project();
    require(f.spring().updates==1 && after.back().image.position.x==before.back().image.position.x &&
        after.back().image.origin.y==before.back().image.origin.y && f.room.scoped_random.state_words()==rng,
        "Native idle updates and transition retention preserve the idle image without random");
}
void invalid_owner_bindings_reject_parameterized() {
    for(unsigned scenario=0;scenario<18;++scenario) {
        Fixture f;const auto foreign=f.definition;
        if(scenario==0) std::swap(f.drawn.live[0].identity,f.drawn.live[1].identity);
        if(scenario==1) f.drawn.live[0].identity=999999;
        if(scenario==2) f.rooms.clear();
        if(scenario==3) f.drawn.dispatch.push_back(0);
        if(scenario==4) f.drawn.dispatch[0]=99;
        if(scenario==5) f.room.entities[1]->present=false;
        if(scenario==6) f.drawn.live[0].visible=false;
        if(scenario==7) f.drawn.live[0].room=&foreign;
        if(scenario==8) f.rooms.push_back(&f.room);
        if(scenario==9) f.drawn.live[0].authored_id=8;
        if(scenario==10) f.drawn.live[0].hud_excluded=true;
        if(scenario==11) f.drawn.live[0].banner=true;
        if(scenario==12) f.drawn.live[0].sort_depth_band=-9999;
        if(scenario==13) f.drawn.live[0].scale.x=-1;
        if(scenario==14) f.room.entities[1]->object=RoomStrawberry{f.spring().body};
        if(scenario==15) f.definition.objects[0].kind=RoomObjectKind::strawberry;
        if(scenario==16) f.definition.objects.push_back(f.definition.objects[0]);
        if(scenario==17) f.rooms.push_back(nullptr);
        rejects([&] { f.project(); });
    }
}
void unsupported_native_states_reject_parameterized() {
    for(unsigned scenario=0;scenario<9;++scenario) {
        Fixture f;auto& spring=f.spring();
        if(scenario==0) spring.wiggler=0.1f;
        if(scenario==1) spring.wiggler=std::numeric_limits<float>::quiet_NaN();
        if(scenario==2) spring.body.collidable=false;
        if(scenario==3) spring.attached=nullptr;
        if(scenario==4) spring.body.collider.reset();
        if(scenario==5) spring.body.collider=Hitbox{6,16,{0,-8}};
        if(scenario==6) spring.body.collider=Hitbox{6,16,{-6,-8}};
        if(scenario==7) spring.body.position.x=std::numeric_limits<float>::infinity();
        if(scenario==8) spring.body.collider->offset.y=0;
        rejects([&] { f.project(); });
    }
}
void invalid_idle_metadata_rejects_parameterized() {
    for(unsigned scenario=0;scenario<16;++scenario) {
        Fixture f;auto& frame=f.catalog.idle;
        if(scenario==0) frame.texture="fixture/bounce";
        if(scenario==1) f.catalog.idle_texture.clear();
        if(scenario==2) frame.sheet.clear();
        if(scenario==3) frame.width=0;
        if(scenario==4) frame.height=-1;
        if(scenario==5) frame.x=-1;
        if(scenario==6) frame.y=4096;
        if(scenario==7) frame.width=4097;
        if(scenario==8) frame.frame_width=0;
        if(scenario==9) frame.frame_height=4097;
        if(scenario==10) frame.offset_x=std::numeric_limits<float>::quiet_NaN();
        if(scenario==11) frame.offset_y=std::numeric_limits<float>::infinity();
        if(scenario==12) frame.offset_x=1;
        if(scenario==13) frame.offset_y=-17;
        if(scenario==14) frame.offset_x=-0.5f;
        if(scenario==15) frame.frame_width=8;
        rejects([&] { f.project(); });
    }
}
void non_spring_dispatch_is_not_projected() {
    Fixture f;f.drawn.live.clear();f.drawn.dispatch.clear();
    f.drawn.live.push_back({draw_order::OwnerKind::wind,f.room.entities[0]->object_identity,-2,&f.definition});
    f.drawn.dispatch={0};require(f.project().empty(),"Unrelated dispatched owners must not acquire Spring commands");
}
void replacement_room_cannot_bind_previous_native_identity() {
    Fixture f;RoomRuntime replacement(f.definition,f.collision);f.rooms={&replacement};
    rejects([&] { f.project(); });
}
void commands_use_live_body_not_authored_playback() {
    Fixture f;f.spring().body.position={-39.125f,-30};
    const auto image=f.project().back().image;
    require(image.position.x==-39.125f && image.position.y==-30,"Commands must use the actual current native body");
}
void odd_logical_width_preserves_half_pixel_origin() {
    Fixture f;f.catalog.idle.frame_width=19;
    require(f.project().back().image.origin.x==6.5f,"Logical bottom-center must not use integer division");
}
std::string catalog_text() {
    std::string text="CSPR1\n";
    for(const auto pin:spring_commands::provenance) text+=std::string(pin)+'\n';
    return text+"floor idle 0 0\n1\nGameplay0 32 48 6 4 -3 -10 18 20 objects/spring/00\n";
}
void catalog_parses_signed_raw_trim_and_bottom_center() {
    const auto text=catalog_text();const auto catalog=spring_commands::parse(text,asset_text::checksum(text));
    require(catalog.idle.offset_x==-3 && catalog.idle.offset_y==-10 && catalog.idle.frame_height==20,
        "Shared frame decoder must retain raw signed atlas offsets and untrimmed dimensions");
}
void malformed_catalog_rejects_parameterized() {
    const auto valid=catalog_text();
    for(unsigned i=0;i<valid.size();++i) {
        const auto truncated=valid.substr(0,i);
        rejects([&] { spring_commands::parse(truncated,asset_text::checksum(truncated)); });
    }
    for(const auto& text:{valid+"extra\n",valid+"\n",std::string("X")+valid.substr(1)})
        rejects([&] { spring_commands::parse(text,asset_text::checksum(text)); });
    for(unsigned pin=0;pin<spring_commands::provenance.size();++pin) {
        auto text=valid;const auto index=6+65*pin;text[index]=text[index]=='0'?'1':'0';
        rejects([&] { spring_commands::parse(text,asset_text::checksum(text)); });
    }
    for(const auto& change:std::vector<std::pair<std::string,std::string>>{
            {"floor idle 0 0","wallLeft idle 0 0"},{"floor idle 0 0","floor bounce 1 0"},
            {"floor idle 0 0","floor idle 0 1"},{"\n1\n","\n2\n"},
            {"objects/spring/00","fixture/unknown"},{"Gameplay0","Unknown"},
            {"6 4 -3 -10","6 4 3 10"},{"18 20 objects","8 20 objects"},
            {"32 48 6 4","4096 48 6 4"},{"objects/spring/00","objects/spring/00 unknown"}}) {
        auto text=valid;const auto index=text.find(change.first);require(index!=std::string::npos,"Valid mutation fixture");
        text.replace(index,change.first.size(),change.second);
        rejects([&] { spring_commands::parse(text,asset_text::checksum(text)); });
    }
    rejects([&] { spring_commands::parse(valid,1); });
}
}
int main() {
    try {
        ordered_outline_and_main_bind_actual_native_owners();
        trim_and_untrimmed_origin_matrix_parameterized();
        shared_geometry_uses_actual_negative_world_arithmetic();
        projection_does_not_mutate_native_state_or_random();
        invalid_owner_bindings_reject_parameterized();
        unsupported_native_states_reject_parameterized();
        invalid_idle_metadata_rejects_parameterized();
        non_spring_dispatch_is_not_projected();
        replacement_room_cannot_bind_previous_native_identity();
        commands_use_live_body_not_authored_playback();
        odd_logical_width_preserves_half_pixel_origin();
        catalog_parses_signed_raw_trim_and_bottom_center();
        malformed_catalog_rejects_parameterized();
        std::cout<<"13 Spring projection behaviors passed\n";
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
