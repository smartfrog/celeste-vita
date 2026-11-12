#include "draw_order.hpp"
#include "jumpthru_commands.hpp"
#include "asset_text.hpp"
#include <iostream>
#include <stdexcept>

using namespace celeste;
namespace {
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
template<class F> void rejects(F operation) {
    try { operation(); } catch(const std::logic_error&) { return; }
    throw std::runtime_error("Invalid JumpThru contract must reject");
}
struct Fixture {
    RoomDefinition definition{"2",{240,-184,320,180},50,{264,-24},{
        {RoomObjectKind::jump_thru,7,{248,-24},40},
        {RoomObjectKind::jump_thru,8,{280,-48},40}}};
    draw_order::AuthoredDecalOwners metadata{&definition,{},0,0};
    StaticWorld collision;
    RoomRuntime room{definition,collision,false,&metadata};
    jumpthru_commands::Catalog catalog{{"Gameplay0",16,24,24,12,0,0,24,16,"objects/jumpthru/wood"}};
    draw_order::DrawProjection drawn;
    std::vector<const RoomRuntime*> rooms{&room};
    Fixture() {
        for(unsigned i=1;i<room.entities.size();++i) drawn.live.push_back({draw_order::OwnerKind::jumpthru_platform,
            room.entities[i]->object_identity,room.entities[i]->authored_id,&definition,-60,i,true,false,false});
        drawn.dispatch={0,1};
    }
    std::vector<jumpthru_commands::Command> project() const { return jumpthru_commands::project(drawn,catalog,rooms); }
};
void source_visual_choices_continue_after_banner_added() {
    RoomDefinition definition{"2",{240,-184,320,180},50,{264,-24},{
        {RoomObjectKind::jump_thru,7,{248,-24},40},
        {RoomObjectKind::spike_up,8,{400,-72},40},
        {RoomObjectKind::spike_up,9,{432,-24},16},
        {RoomObjectKind::spike_up,10,{448,-16},16}}};
    draw_order::AuthoredDecalOwners metadata{&definition,{},4,0};
    for(unsigned i=0;i<4;++i) metadata.owners.push_back({draw_order::OwnerKind::decal,
        0x6000000000000001ull+i,int(i),&definition,9000,i,true,false,true,"fixture_banner"});
    StaticWorld collision;RoomRuntime room(definition,collision,false,&metadata);
    const auto& platform=*room.entities[1];
    require(room.jump_thru_visual(platform.object_identity).cells==std::vector<std::pair<int,int>>{{0,1},{1,1},{1,1},{1,0},{2,1}},
        "Visual JumpThru choices must continue the detached Banner stream (1,1,0), not physical (0,0,1)");
    require(platform.image_cells==std::vector<std::pair<int,int>>{{0,1},{1,0},{1,0},{1,1},{2,1}},"Physical cells must not become visual choices");
    RoomRuntime baseline(definition,collision);
    require(room.scoped_random.calls()==15 && room.scoped_random.state_words()==baseline.scoped_random.state_words() &&
        room.random_events==baseline.random_events,"Detached initialization must preserve physical calls and observer events");
}
void multiple_platforms_continue_one_detached_stream() {
    Fixture f;PresentationRandom expected(50);
    for(unsigned i=1;i<f.room.entities.size();++i) {
        const auto& entity=*f.room.entities[i];const auto& cells=f.room.jump_thru_visual(entity.object_identity).cells;
        for(unsigned piece=1;piece<4;++piece) {
            expected.next(1);
            require(cells[piece].second==expected.next(2),"Every platform must continue the same visual random stream");
        }
    }
    require(f.room.scoped_random.calls()==12 && f.room.random_events.size()==12,"Visual draws must not duplicate physical events");
}
void metadata_null_keeps_visual_state_absent() {
    Fixture f;RoomRuntime baseline(f.definition,f.collision);
    rejects([&] { baseline.jump_thru_visual(baseline.entities[1]->object_identity); });
    require(baseline.entities[1]->image_cells==f.room.entities[1]->image_cells,"Null metadata must preserve legacy physical choices");
}
void visual_projection_refuses_missing_visual_state() {
    Fixture f;RoomRuntime baseline(f.definition,f.collision);
    f.rooms={&baseline};
    for(unsigned i=0;i<f.drawn.live.size();++i) f.drawn.live[i].identity=baseline.entities[i+1]->object_identity;
    rejects([&] { f.project(); });
}
void source_clipping_and_ordered_command_fields() {
    Fixture f;const auto commands=f.project();require(commands.size()==10,"One command per ordered Image");
    for(unsigned i=0;i<commands.size();++i) {
        const auto& command=commands[i];const auto& image=command.image;const unsigned platform=i/5+1,piece=i%5;
        const auto& entity=*f.room.entities[platform];const auto cell=f.room.jump_thru_visual(entity.object_identity).cells[piece];
        require(command.piece==piece && command.authored_id==entity.authored_id && command.dispatch_index==platform-1 &&
            image.identity==entity.object_identity && image.room=="2","Commands must bind actual entity, semantic id, piece and dispatch");
        require(image.source_x==16+8*cell.first && image.source_y==24+8*cell.second &&
            image.source_width==8 && image.source_height==(cell.second?4:8),"Source row1 clips 8x4, not logical 8x8");
        require(image.position.x==entity.position().x+8*piece && image.position.y==entity.position().y &&
            image.origin.x==0 && image.origin.y==0 && image.scale.x==1 && image.scale.y==1 && image.rotation==0 &&
            image.effects=="None" && image.color.r==255 && image.color.g==255 && image.color.b==255 && image.color.a==255 &&
            image.sheet=="Gameplay0" && image.texture=="objects/jumpthru/wood","Source Image defaults must remain exact");
    }
}
void projection_is_read_only_across_updates_and_repeated_draws() {
    Fixture f;const auto state=f.room.scoped_random.state_words();const auto before=f.room.jump_thru_visual(f.room.entities[1]->object_identity).cells;
    f.project();f.room.update(1.f/60,false);f.project();f.room.update(1.f/60,true);f.project();
    require(f.room.scoped_random.state_words()==state && f.room.jump_thru_visual(f.room.entities[1]->object_identity).cells==before,
        "Updates, transition retention and projections cannot mutate visual choices or RNG");
}
void fresh_room_identity_cannot_reuse_retained_visual_choices() {
    Fixture f;RoomRuntime replacement(f.definition,f.collision,false,&f.metadata);
    const auto identity=f.room.entities[1]->object_identity;
    require(identity!=replacement.entities[1]->object_identity,"Reload must allocate fresh native entity identities");
    rejects([&] { replacement.jump_thru_visual(identity); });
    require(f.room.jump_thru_visual(identity).cells.size()==5,"Retained room keeps its own visual choices");
}
void invalid_bindings_reject_parameterized() {
    for(unsigned scenario=0;scenario<12;++scenario) {
        Fixture f;
        const auto foreign=f.definition;
        if(scenario==0) std::swap(f.drawn.live[0].identity,f.drawn.live[1].identity);
        if(scenario==1) f.drawn.live[0].identity=999999;
        if(scenario==2) f.rooms.clear();
        if(scenario==3) f.drawn.dispatch.push_back(0);
        if(scenario==4) f.drawn.dispatch[0]=99;
        if(scenario==5) f.room.entities[1]->present=false;
        if(scenario==6) f.drawn.live[0].visible=false;
        if(scenario==7) f.catalog.wood.offset_y=-1;
        if(scenario==8) f.catalog.wood.frame_width=16;
        if(scenario==9) f.rooms.push_back(&f.room);
        if(scenario==10) f.room.entities[1]->object=RoomJumpThru{Body{{248,-24},Hitbox{48,5,{}},true}};
        if(scenario==11) f.drawn.live[0].room=&foreign;
        rejects([&] { f.project(); });
    }
}
void visual_cell_corruption_rejects_parameterized() {
    for(unsigned scenario=0;scenario<3;++scenario) {
        Fixture f;
        auto& cells=const_cast<JumpThruVisual&>(f.room.jump_thru_visual(f.room.entities[1]->object_identity)).cells;
        if(scenario==0) cells.pop_back();
        if(scenario==1) cells[1].second=2;
        if(scenario==2) cells[1].first=2;
        rejects([&] { f.project(); });
    }
}
void full_body_plus_minus_one_solid_probes_parameterized() {
    for(unsigned scenario=0;scenario<4;++scenario) {
        StaticWorld world;
        Body left{{247,-24},Hitbox{1,5,{}},true},right{{288,-24},Hitbox{1,5,{}},true};
        if(scenario&1) world.solids.push_back(&left);
        if(scenario&2) world.solids.push_back(&right);
        PresentationRandom random(50);Body platform{{248,-24},Hitbox{40,5,{}},true};
        const auto cells=choose_jump_thru_cells(platform,random,world);
        require(cells.front()==std::make_pair(0,(scenario&1)?0:1) && cells.back()==std::make_pair(2,(scenario&2)?0:1) && random.calls()==6,
            "Full-body +/-1 probes must preserve exact touching boundaries and random calls");
    }
}
void single_column_uses_left_edge_without_random() {
    StaticWorld world;PresentationRandom random(50);Body platform{{0,0},Hitbox{8,5,{}},true};
    require(choose_jump_thru_cells(platform,random,world)==std::vector<std::pair<int,int>>{{0,1}} && random.calls()==0,
        "Single column follows Source first-column precedence");
}
void full_map_grid_probes_use_body_not_origin_point() {
    TileGrid grid(7,1,{1,0,0,0,0,0,1});Body solid{{},std::nullopt,true,&grid};
    StaticWorld world;world.solids.push_back(&solid);
    PresentationRandom random(50);Body platform{{8,0},Hitbox{40,5,{}},true};
    const auto cells=choose_jump_thru_cells(platform,random,world);
    require(cells.front()==std::make_pair(0,0) && cells.back()==std::make_pair(2,0),
        "Both edge probes must intersect full-map tiles using the shifted full body");
}
void catalog_truncation_trailing_and_pin_reject_parameterized() {
    const std::string header="CJTC1\n256d58907b477c9c7f42bbcd5813fe7486f0881b91d504a622cf2f5582c4019e\n"
        "45847f23970911b07541e4bc367cbd156f3b4b1846b63b33d3fed9c7b65ebf6b\n"
        "aa87a22589821fc3781672126e68f2195fb46348f261013d8a01c070b53821d3\n"
        "1f23b1f35544a3751ffec170b0230c7c9513000ab1549f78ebb9cb9f4203c8d9\n"
        "b75f913d315bd641c35a4990d9041b238c0d9ef3f8b1247ec557de8a9defc1cc\n";
    const auto valid=header+"Gameplay0 16 24 24 12 0 0 24 16 objects/jumpthru/wood\n";
    require(jumpthru_commands::parse(valid,asset_text::checksum(valid)).wood.height==12,"Logical frame height 16 need not fit clipped height 12");
    for(unsigned i=0;i<valid.size();++i) {
        const auto truncated=valid.substr(0,i);rejects([&] { jumpthru_commands::parse(truncated,asset_text::checksum(truncated)); });
    }
    for(const auto& text:{valid+"extra\n",std::string("X")+valid.substr(1),header+"Gameplay0 16 24 24 12 0 1 24 16 objects/jumpthru/wood\n"})
        rejects([&] { jumpthru_commands::parse(text,asset_text::checksum(text)); });
    for(unsigned pin=0;pin<5;++pin) {
        auto changed=valid;const auto index=6+65*pin;changed[index]=changed[index]=='0'?'1':'0';
        rejects([&] { jumpthru_commands::parse(changed,asset_text::checksum(changed)); });
    }
    rejects([&] { jumpthru_commands::parse(valid,1); });
}
}
int main() {
    try {
        source_visual_choices_continue_after_banner_added();
        multiple_platforms_continue_one_detached_stream();
        metadata_null_keeps_visual_state_absent();
        visual_projection_refuses_missing_visual_state();
        source_clipping_and_ordered_command_fields();
        projection_is_read_only_across_updates_and_repeated_draws();
        fresh_room_identity_cannot_reuse_retained_visual_choices();
        invalid_bindings_reject_parameterized();
        visual_cell_corruption_rejects_parameterized();
        full_body_plus_minus_one_solid_probes_parameterized();
        single_column_uses_left_edge_without_random();
        full_map_grid_probes_use_body_not_origin_point();
        catalog_truncation_trailing_and_pin_reject_parameterized();
        std::cout<<"13 JumpThru behaviors passed\n";
    }
    catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
