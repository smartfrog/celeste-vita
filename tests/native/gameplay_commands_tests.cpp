#include "gameplay_commands.hpp"
#include "asset_text.hpp"
#include "lifecycle_fixture.hpp"
#include <algorithm>
#include <cstring>
#include <iostream>
#include <sstream>
#include <stdexcept>

using namespace celeste;
namespace {
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
template<class F> void rejects(F operation,const char* text) {
    try { operation(); }
    catch(const std::invalid_argument& error) {
        require(std::string(error.what()).find(text)!=std::string::npos,"Failure must identify the violated gameplay contract");
        return;
    }
    throw std::runtime_error("Invalid gameplay producer contract was accepted");
}
struct Fixture {
    RoomDefinition room;
    draw_order::DrawProjection projection;
    std::vector<strawberry_commands::Command> berries;
    std::vector<spike_commands::Command> spikes;
    std::vector<terrain::Sheet> sheets{{"Fixture",64,64}};
    gameplay_commands::Inputs inputs;
    Fixture() {
        room.name="fixture";
        projection.live={{draw_order::OwnerKind::strawberry,12,7,&room,-100},
                         {draw_order::OwnerKind::spikes,13,8,&room,-1}};
        projection.dispatch={0,1};
        strawberry_commands::Command berry;
        berry.identity=12;berry.room="fixture";berry.authored_id=7;berry.sheet="Fixture";
        berry.source_width=4;berry.source_height=4;
        berries.push_back(berry);
        spike_commands::Command spike;
        spike.identity=13;spike.room="fixture";spike.authored_id=8;spike.sheet="Fixture";
        spike.source_width=4;spike.source_height=4;
        spikes.push_back(spike);
        inputs.strawberries=&berries;inputs.spikes=&spikes;inputs.sheets=&sheets;
    }
    gameplay_commands::Schedule assemble() const { return gameplay_commands::assemble(projection,inputs); }
};
void dispatch_order_wins_over_family_and_depth() {
    Fixture fixture;
    const auto schedule=fixture.assemble();
    require(schedule.commands().size()==2 && schedule.commands()[0].image.identity==12 &&
            schedule.commands()[1].image.identity==13,"Actual dispatch, not depth/kind, determines global command order");
    require(schedule.ranges().size()==2 && schedule.ranges()[0].begin==0 && schedule.ranges()[0].end==1 &&
            schedule.ranges()[1].begin==1 && schedule.ranges()[1].end==2,"Dispatch ranges partition the flat schedule");
}
void invalid_inputs_reject_parameterized() {
    for(unsigned scenario=0;scenario<19;++scenario) {
        Fixture f;
        const char* message="";
        if(scenario==0) { f.projection.dispatch[0]=99;message="dispatch index"; }
        if(scenario==1) { f.projection.dispatch[1]=0;message="dispatch index"; }
        if(scenario==2) { f.projection.dispatch.pop_back();message="dispatch membership"; }
        if(scenario==3) { f.projection.live[1].identity=12;message="owner identity"; }
        if(scenario==4) { f.inputs.spikes=nullptr;message="Missing gameplay producer"; }
        if(scenario==5) { f.spikes[0].identity=999;message="no live gameplay owner"; }
        if(scenario==6) { std::swap(f.spikes[0].identity,f.berries[0].identity);message="kind/dispatch"; }
        if(scenario==7) { f.spikes[0].authored_id=99;message="room/entity"; }
        if(scenario==8) { f.spikes[0].room="outgoing";message="room/entity"; }
        if(scenario==9) { f.spikes[0].piece=1;message="component piece"; }
        if(scenario==10) { f.spikes.push_back(f.spikes[0]);message="component piece"; }
        if(scenario==11) { f.projection.decal_gap_rooms.push_back(&f.room);message="Unmapped authored"; }
        if(scenario==12) { f.projection.live[0].kind=static_cast<draw_order::OwnerKind>(999);message="Unknown gameplay owner kind"; }
        if(scenario==13) { f.inputs.sheets=nullptr;message="Missing original gameplay sheet"; }
        if(scenario==14) { f.sheets.push_back(f.sheets[0]);message="duplicate gameplay sheet"; }
        if(scenario==15) { f.berries[0].source_x=63;message="rectangle exceeds"; }
        if(scenario==16) { f.projection.live[1].visible=false;message="dispatch membership"; }
        if(scenario==17) { f.projection.live[1].hud_excluded=true;message="dispatch membership"; }
        if(scenario==18) { f.inputs.empty.push_back({999,gameplay_commands::EmptyReason::wind_has_no_capture_calls});message="Unused empty"; }
        rejects([&] { f.assemble(); },message);
    }
}
void producer_subsequence_cannot_be_resorted() {
    Fixture f;
    f.projection.live.push_back({draw_order::OwnerKind::spikes,14,9,&f.room,-1});
    f.projection.dispatch.push_back(2);
    auto second=f.spikes[0];second.identity=14;second.authored_id=9;
    f.spikes.insert(f.spikes.begin(),second);
    rejects([&] { f.assemble(); },"subsequence disagrees");
}
void same_family_identity_bijection_requires_semantics() {
    Fixture f;
    f.projection.live.push_back({draw_order::OwnerKind::spikes,14,9,&f.room,-1});
    f.projection.dispatch.push_back(2);
    auto second=f.spikes[0];second.identity=14;second.authored_id=9;f.spikes.push_back(second);
    std::swap(f.spikes[0].identity,f.spikes[1].identity);
    rejects([&] { f.assemble(); },"room/entity");
}
void explicit_empty_and_hud_policy_is_visible() {
    RoomDefinition room;room.name="fixture";
    draw_order::DrawProjection projection;
    projection.live={{draw_order::OwnerKind::wind,1,-2,&room},
        {draw_order::OwnerKind::scene_helper,2,-1,&room},
        {draw_order::OwnerKind::particle_system_back,3},
        {draw_order::OwnerKind::particle_system_front,4},
        {draw_order::OwnerKind::hud_display,5,-1,nullptr,0,0,false,true}};
    projection.dispatch={3,1,0,2};
    gameplay_commands::Inputs inputs;
    using Reason=gameplay_commands::EmptyReason;
    inputs.empty={{1,Reason::wind_has_no_capture_calls},{2,Reason::scene_helper_has_no_capture_calls},
                  {3,Reason::particle_system_has_no_active_images},{4,Reason::particle_system_has_no_active_images}};
    const auto schedule=gameplay_commands::assemble(projection,inputs);
    require(schedule.commands().empty() && schedule.ranges().size()==4 && schedule.excluded().size()==1 &&
        schedule.excluded()[0].identity==5,"Excluded HUD is not silently mapped empty or dispatched");
    for(const auto& range:schedule.ranges()) require(range.begin==0 && range.end==0 && range.empty.has_value(),"Empty dispatch records explicit capture policy");
}
void required_particle_mid_is_not_silently_empty() {
    draw_order::DrawProjection projection;
    projection.live={{draw_order::OwnerKind::particle_system_mid,1}};projection.dispatch={0};
    gameplay_commands::Inputs inputs;
    rejects([&] { gameplay_commands::assemble(projection,inputs); },"Particle mid requires committed integration");
    inputs.empty={{1,gameplay_commands::EmptyReason::particle_system_has_no_active_images}};
    rejects([&] { gameplay_commands::assemble(projection,inputs); },"policy does not cover");
}
void result_owns_commands_and_readonly_reassembly_is_stable() {
    Fixture f;
    const auto first=f.assemble();
    for(unsigned i=0;i<4;++i) {
        const auto next=f.assemble();
        require(next.commands()[0].geometry.vertices==first.commands()[0].geometry.vertices &&
                next.commands()[1].image.identity==13 && f.spikes[0].piece==0 && f.projection.dispatch==std::vector<std::size_t>{0,1},
                "Repeated const assembly must neither change inputs nor order");
    }
    f.berries[0].sheet="changed";f.berries.clear();f.projection.live.clear();
    require(first.commands()[0].image.sheet=="Fixture" && first.ranges()[0].room=="fixture", "Owned immutable schedule must not alias mutable producer input");
}
void zero_clip_nonfinite_geometry_words_are_not_sanitized() {
    Fixture f;
    f.berries[0].source_width=0;f.berries[0].origin.x=0;
    const auto expected=decal_commands::project_geometry(f.berries[0],64,64);
    const auto schedule=f.assemble();
    require(!schedule.commands()[0].geometry.finite && schedule.commands()[0].geometry.vertices==expected.vertices,
        "Logical Source geometry retains all signed IEEE words including generated NaNs");
}
void cached_player_binds_original_sheet_clip_and_trim_once() {
    PlayerFrameBank bank;
    bank.pages=1;
    bank.frames.push_back({"characters/player/idle00",0,3,5,4,6,2,3,8,10,{},0,false});
    std::istringstream text("CPLAYERDRAW1 1 characters/player/idle00 0 3 5 4 6 2 3 8 10 Gameplay0 4096 4096 100 200 4 6");
    const auto mapping=read_player_draw_mapping(text,bank);
    std::vector<PlayerDraw> draws{{0,{20,30},{4,10},{-1,1},0,{}},{0,{21,31},{4,10},{1,1},0,{}}};
    std::vector<terrain::Sheet> sheets{{"Gameplay0",4096,4096}};
    gameplay_commands::CachedPlayer player{42,true,bank,mapping,draws};
    draw_order::DrawProjection projection;projection.live={{draw_order::OwnerKind::player,42}};projection.dispatch={0};
    gameplay_commands::Inputs inputs;inputs.player=&player;inputs.sheets=&sheets;
    const auto schedule=gameplay_commands::assemble(projection,inputs);
    const auto& image=schedule.commands()[0].image;
    require(image.identity==42 && image.source_x==100 && image.source_y==200 && image.source_width==4 && image.source_height==6 &&
        image.origin.x==2 && image.origin.y==7 && image.scale.x==-1 && schedule.commands()[0].sheet_width==4096 &&
        schedule.commands()[0].component==gameplay_commands::Component::player_sprite &&
        schedule.commands()[1].component==gameplay_commands::Component::sprite,"Player uses original atlas, MTexture origin minus trim, and ordered component attribution");
    require(draws[0].origin.x==4 && bank.frames[0].u==3 && bank.frames[0].v==5,"Binding cached Player never mutates packed native metadata or cached Draw output");
}
void unused_player_mapping_alias_is_validated_before_assembly() {
    PlayerFrameBank bank;bank.pages=1;
    bank.frames={{"used",0,1,2,4,6,0,0,4,6,{},0,false},{"unused",0,5,6,4,6,0,0,4,6,{},0,false}};
    std::vector<LogicalPlayerFrame> mapping{{"Fixture",64,64,10,20,4,6,"used"},{"Fixture",64,64,30,40,4,6,"missing"}};
    std::vector<PlayerDraw> draws{{0,{},{},{1,1},0,{}},{0,{},{},{1,1},0,{}}};
    gameplay_commands::CachedPlayer player{42,true,bank,mapping,draws};
    draw_order::DrawProjection projection;projection.live={{draw_order::OwnerKind::player,42}};projection.dispatch={0};
    std::vector<terrain::Sheet> sheets{{"Fixture",64,64}};
    gameplay_commands::Inputs inputs;inputs.player=&player;inputs.sheets=&sheets;
    rejects([&] { gameplay_commands::assemble(projection,inputs); },"original atlas alias");
}
void native_jumpthru_and_spring_streams_keep_component_and_dispatch_indices() {
    RoomDefinition definition{"fixture",{-128,-184,320,180},50,{-64,-32},{
        {RoomObjectKind::spring,7,{-40,-32}}, {RoomObjectKind::jump_thru,8,{24,-48},40}}};
    draw_order::AuthoredDecalOwners metadata{&definition,{},0,0};
    Body support{{-128,-32},Hitbox{256,8,{}},true};StaticWorld collision{{&support},{}};
    RoomRuntime room(definition,collision,false,&metadata);
    draw_order::DrawProjection projection;
    projection.live={{draw_order::OwnerKind::spring,room.entities[1]->object_identity,7,&definition,-8501},
        {draw_order::OwnerKind::jumpthru_platform,room.entities[2]->object_identity,8,&definition,-60}};
    projection.dispatch={1,0};
    std::vector<const RoomRuntime*> rooms{&room};
    spring_commands::Catalog spring_catalog{{"Fixture",32,48,6,4,-3,-10,18,20,"fixture/idle"},"fixture/idle"};
    jumpthru_commands::Catalog jump_catalog{{"Gameplay0",16,24,24,12,0,0,24,16,"objects/jumpthru/wood"}};
    auto springs=spring_commands::project(projection,spring_catalog,rooms);
    auto jumps=jumpthru_commands::project(projection,jump_catalog,rooms);
    std::vector<terrain::Sheet> sheets{{"Fixture",128,128},{"Gameplay0",4096,4096}};
    gameplay_commands::Inputs inputs;inputs.springs=&springs;inputs.jumpthrus=&jumps;inputs.sheets=&sheets;
    const auto random=room.scoped_random.state_words();const auto events=room.random_events;
    const auto schedule=gameplay_commands::assemble(projection,inputs);
    require(schedule.commands().size()==14 && schedule.ranges()[0].end==5 && schedule.ranges()[1].begin==5,
        "Actual JumpThru visitor precedes all nine Spring commands according to dispatch");
    for(unsigned piece=0;piece<9;++piece) require(schedule.commands()[5+piece].piece==piece &&
        schedule.commands()[5+piece].component==(piece==8?gameplay_commands::Component::sprite:gameplay_commands::Component::direct),
        "Spring outline commands are direct entity calls, followed by Sprite, never universal image_count");
    for(unsigned repeat=0;repeat<3;++repeat) gameplay_commands::assemble(projection,inputs);
    require(room.scoped_random.state_words()==random && room.random_events==events && std::get<RoomSpring>(room.entities[1]->object).updates==0,
        "Assembling native producers must not reinitialize, update, or consume room RNG");
}
void spring_missing_last_component_is_not_complete() {
    Fixture f;f.projection.live.resize(1);f.projection.dispatch={0};f.projection.live[0].kind=draw_order::OwnerKind::spring;
    f.inputs.strawberries=nullptr;f.inputs.spikes=nullptr;
    std::vector<spring_commands::Command> springs;
    for(unsigned piece=0;piece<8;++piece) springs.push_back({f.berries[0],7,piece,0});
    f.inputs.springs=&springs;
    rejects([&] { f.assemble(); },"Incomplete Spring component stream");
}
void actual_banner_and_decal_streams_preserve_component_pieces() {
    constexpr std::uint64_t image_identity=0x600000000000005aull,banner_identity=0x600000000000005bull;
    RoomDefinition definition{"fixture",{0,0,64,64},49,{0,0},{}};
    draw_order::DrawOwner image_owner{draw_order::OwnerKind::decal,image_identity,0,&definition,9000,0,true,false,false,"image",{16,16}};
    draw_order::DrawOwner banner_owner{draw_order::OwnerKind::decal,banner_identity,1,&definition,9000,1,true,false,true,"banner",{32,16}};
    draw_order::AuthoredDecalOwners metadata{&definition,{image_owner,banner_owner},2,0};
    StaticWorld collision;RoomRuntime room(definition,collision,false,&metadata);
    decal_commands::StaticDecalCatalog catalog;
    catalog.families={{"Fixture",8,8,4,4,0,0,4,4,"image"},{"Fixture",16,16,4,4,0,0,4,4,"banner"}};
    catalog.owners={{image_identity,"fixture",true,0,0,"image"}};catalog.deferred={{banner_identity,"fixture",true,1,"banner"}};
    catalog.banners={{1,1,2,2,0.1f,false,0,false,1}};
    draw_order::DrawProjection projection{{image_owner,banner_owner},{1,0},{}};
    std::vector<const RoomRuntime*> rooms{&room};
    auto decals=decal_commands::project(projection,catalog,&rooms);
    std::vector<terrain::Sheet> sheets{{"Fixture",64,64}};
    gameplay_commands::Inputs inputs;inputs.decals=&decals;inputs.sheets=&sheets;
    const auto schedule=gameplay_commands::assemble(projection,inputs);
    require(schedule.commands().size()==3 && schedule.commands()[0].component==gameplay_commands::Component::banner &&
        schedule.commands()[1].piece==1 && schedule.commands()[2].component==gameplay_commands::Component::decal_image,
        "Actual per-owner Banner slices remain together before DecalImage despite storage order");
    std::swap(decals.commands[0],decals.commands[1]);
    rejects([&] { gameplay_commands::assemble(projection,inputs); },"component piece");
}
void deferred_decals_never_silently_disappear() {
    Fixture f;decal_commands::DecalProjection decals;decals.deferred.push_back({90,"fixture",true,0,"banner"});
    f.inputs.decals=&decals;
    rejects([&] { f.assemble(); },"Deferred gameplay decal");
}
void global_terrain_uses_catalog_visitor_and_camera_not_room_owner() {
    std::string text="CSTV1\n";
    for(unsigned i=0;i<4;++i) text+=std::string(64,'a')+'\n';
    text+="0 0 8 8 8 1\n1\nFixture 64 64\n1\nfixture/tile 0 8 16 8 8 0 0 8 8 255 255 255 255 1\n"
          "2\nB 10000 2\n0 0 0\n7 7 0\nF -10000 1\n1 1 0\n";
    const auto catalog=terrain::parse(text,asset_text::checksum(text));
    gameplay_commands::TerrainInput terrain{catalog,10,11,{0,0},{8,8}};
    draw_order::DrawProjection projection{{{draw_order::OwnerKind::background_tiles,10},
        {draw_order::OwnerKind::solid_tiles,11}},{1,0},{}};
    gameplay_commands::Inputs inputs;inputs.terrain=&terrain;inputs.sheets=&catalog.sheets();
    const auto first=gameplay_commands::assemble(projection,inputs);
    require(first.commands().size()==2 && first.commands()[0].image.identity==11 && first.commands()[1].image.identity==10 &&
        first.commands()[0].image.position.x==8 && first.commands()[0].image.position.y==8 && first.ranges()[0].room.empty(),
        "Global terrain visitors cull using camera and keep their persistent owners in actual dispatch order");
    terrain.camera={56,56};
    const auto next=gameplay_commands::assemble(projection,inputs);
    require(next.commands().size()==1 && next.commands()[0].image.position.x==56 && next.ranges()[0].begin==next.ranges()[0].end,
        "Global terrain survives camera movement and explicitly supports a legitimately culled empty layer");
}
void assembly_does_not_add_player_draw_or_change_subsequent_state() {
    native_test::LifecycleFixture fixture;
    FirstRoomSession observed(fixture.world,fixture.frames),baseline(fixture.world,fixture.frames);
    std::vector<LogicalPlayerFrame> mapping;
    for(const auto& frame:fixture.frames.frames) mapping.push_back({"Fixture",64,64,1,1,frame.width,frame.height,frame.name});
    std::vector<terrain::Sheet> sheets{{"Fixture",64,64}};
    for(unsigned tick=0;tick<80;++tick) {
        observed.step(1.f/60,{});baseline.step(1.f/60,{});
        const auto cached=observed.draw();const auto expected=baseline.draw();
        gameplay_commands::CachedPlayer player{observed.player().object_identity(),std::string(observed.phase())=="live",fixture.frames,mapping,cached};
        draw_order::DrawProjection projection{{{draw_order::OwnerKind::player,player.identity}},{0},{}};
        gameplay_commands::Inputs inputs;inputs.player=&player;inputs.sheets=&sheets;
        const auto first=gameplay_commands::assemble(projection,inputs);
        const auto second=gameplay_commands::assemble(projection,inputs);
        require(first.commands().size()==expected.size() && second.commands().size()==cached.size() &&
            observed.random().state_words()==baseline.random().state_words() && observed.random().calls()==baseline.random().calls(),
            "Normal Draw occurs once on both paths; repeated assembly never changes RNG or command counts");
        for(unsigned i=0;i<cached.size();++i) require(cached[i].position.x==expected[i].position.x && cached[i].position.y==expected[i].position.y &&
            first.commands()[i].geometry.vertices==second.commands()[i].geometry.vertices,"Cached Player geometry is stable without calling Draw again");
        require(observed.player().actor().body.position.x==baseline.player().actor().body.position.x &&
            observed.player().actor().body.position.y==baseline.player().actor().body.position.y &&
            observed.context().clock.frame_counter==baseline.context().clock.frame_counter,"Assembly toggling leaves subsequent physical and clock state unchanged");
    }
}
}
int main() {
    try {
        dispatch_order_wins_over_family_and_depth();
        invalid_inputs_reject_parameterized();
        producer_subsequence_cannot_be_resorted();
        same_family_identity_bijection_requires_semantics();
        explicit_empty_and_hud_policy_is_visible();
        required_particle_mid_is_not_silently_empty();
        result_owns_commands_and_readonly_reassembly_is_stable();
        zero_clip_nonfinite_geometry_words_are_not_sanitized();
        cached_player_binds_original_sheet_clip_and_trim_once();
        unused_player_mapping_alias_is_validated_before_assembly();
        native_jumpthru_and_spring_streams_keep_component_and_dispatch_indices();
        spring_missing_last_component_is_not_complete();
        actual_banner_and_decal_streams_preserve_component_pieces();
        deferred_decals_never_silently_disappear();
        global_terrain_uses_catalog_visitor_and_camera_not_room_owner();
        assembly_does_not_add_player_draw_or_change_subsequent_state();
    }
    catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
