#include "session_catalog_fixture.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>

using namespace celeste;
using namespace celeste::diagnostic;
namespace {
void require(bool value,const char* message) { if(!value) throw std::runtime_error(message); }
template<class F> void rejects(F operation,const char* message) {
    try { operation(); } catch(const std::logic_error&) { return; }
    throw std::runtime_error(message);
}
void same_configuration_state(const FirstRoomSession& actual,const FirstRoomSession& expected) {
    require(actual.room_definition()==expected.room_definition(),"Catalog definitions must remain borrowed, not copied");
    require(actual.random().initial_seed()==expected.random().initial_seed() && actual.random().calls()==expected.random().calls() &&
        actual.random().state_words()==expected.random().state_words(),"Forwarding must preserve the diagnostic seed and global RNG stream");
    require(actual.stats().hit_checkpoint==expected.stats().hit_checkpoint && actual.stats().loads==expected.stats().loads &&
        actual.stats().reloads==expected.stats().reloads && actual.stats().scoped_room_random_calls==expected.stats().scoped_room_random_calls,
        "Forwarding must preserve checkpoint and physical room lifecycle state");
    require(actual.player().actor().body.position.x==expected.player().actor().body.position.x &&
        actual.player().actor().body.position.y==expected.player().actor().body.position.y &&
        actual.player().state_machine().state()==expected.player().state_machine().state(),"Constructor integration must not change physical playback");
    require(actual.presentation().pose().frame==expected.presentation().pose().frame &&
        actual.presentation().pose().animation==expected.presentation().pose().animation,"The retained frame bank must drive the same presentation");
    if(actual.room_definition()) {
        const auto& room=native_test::catalog_room(actual,*actual.room_definition());
        const auto& other=native_test::catalog_room(expected,*expected.room_definition());
        require(room.scoped_random.calls()==other.scoped_random.calls() && room.scoped_random.state_words()==other.scoped_random.state_words() &&
            room.random_events==other.random_events,"Detached visuals must not perturb physical room randomness");
        require(room.banners().size()==other.banners().size(),"Every borrowed Banner must be initialized");
        for(const auto& banner:room.banners()) require(banner.sine_timer==other.banner_phase(banner.authored_identity),"Borrowed Banner phases must match core construction");
    }
}
void initial_construction_forwards_exact_catalog_and_metadata() {
    native_test::SessionCatalogFixture fixture;
    Session session(fixture.physical.world,fixture.physical.frames,true,12345,&fixture.catalog,&fixture.owners);
    FirstRoomSession expected(fixture.physical.world,fixture.physical.frames,true,12345,&fixture.catalog,&fixture.owners);
    same_configuration_state(*session.lifecycle(),expected);
    require(native_test::catalog_room(*session.lifecycle(),fixture.catalog.first()).banners().size()==1,"Visual initialization must precede the first update");
}
void repeated_reset_retains_configuration_parameterized() {
    for(const bool checkpoint:{false,true}) {
        native_test::SessionCatalogFixture fixture;
        fixture.physical.frames.frames.push_back(fixture.physical.frames.frames.front());
        for(auto& animation:fixture.physical.frames.animations) animation.frames={2};
        Session session(fixture.physical.world,fixture.physical.frames,checkpoint,12345,&fixture.catalog,&fixture.owners);
        for(unsigned reset=1;reset<=2;++reset) {
            for(unsigned frame=0;frame<45;++frame) session.step({});
            const auto old=session.lifecycle()->object_identity();
            const auto old_scope=native_test::catalog_room(*session.lifecycle(),fixture.catalog.first()).scoped_random.object_identity();
            session.step({{},true,false});
            FirstRoomSession expected(fixture.physical.world,fixture.physical.frames,checkpoint,12345,&fixture.catalog,&fixture.owners);
            same_configuration_state(*session.lifecycle(),expected);
            require(session.resets()==reset && session.lifecycle()->object_identity()!=old &&
                native_test::catalog_room(*session.lifecycle(),fixture.catalog.first()).scoped_random.object_identity()!=old_scope,
                "Reset must reconstruct fresh owners from the original borrowed configuration");
            require(session.presentation()->pose().frame==2,"Reset must retain the caller's distinctive frame bank");
        }
    }
}
void natural_reload_retains_borrowed_visual_metadata() {
    native_test::SessionCatalogFixture fixture;
    Session session(fixture.physical.world,fixture.physical.frames,false,7,&fixture.catalog,&fixture.owners);
    const auto identity=fixture.owners.front().owners.front().identity;
    const auto initial=native_test::catalog_room(*session.lifecycle(),fixture.catalog.first()).banner_phase(identity);
    for(unsigned frame=0;frame<40;++frame) session.step({});
    for(unsigned frame=0;!session.player().death().dead && frame<180;++frame) {
        Sample sample;sample.player.x=1;sample.player.jump={frame==0,frame==0,frame==1};session.step(sample);
    }
    require(session.lifecycle()->pending_corpse(),"Natural fixture hazard must queue a corpse");
    for(unsigned frame=0;session.lifecycle()->stats().reloads==0 && frame<240;++frame) session.step({});
    require(session.lifecycle()->stats().reloads==1 && session.resets()==0 &&
        native_test::catalog_room(*session.lifecycle(),fixture.catalog.first()).banner_phase(identity)==initial,
        "Natural lifecycle reload must keep the same metadata binding and reinitialize visual phases");
}
void null_configuration_preserves_existing_automatic_behavior() {
    native_test::LifecycleFixture fixture;Session session(fixture.world,fixture.frames);
    FirstRoomSession expected(fixture.world,fixture.frames);
    for(unsigned frame=0;frame<45;++frame) { session.step({});expected.step(1.f/60,{});same_configuration_state(*session.lifecycle(),expected); }
    session.step({{},true,false});FirstRoomSession fresh(fixture.world,fixture.frames);same_configuration_state(*session.lifecycle(),fresh);
    require(session.lifecycle()->room_definition()==nullptr,"Default calls must not activate the catalog branch");
}
void invalid_metadata_bindings_reject_parameterized() {
    for(unsigned scenario=0;scenario<4;++scenario) {
        native_test::SessionCatalogFixture fixture;
        auto alias=fixture.catalog.first();
        if(scenario==1) fixture.owners.pop_back();
        if(scenario==2) fixture.owners.front().room=&alias;
        if(scenario==3) fixture.owners.front().background_count=-1;
        rejects([&] { Session session(fixture.physical.world,fixture.physical.frames,false,0,scenario==0?nullptr:&fixture.catalog,&fixture.owners); },
            "Invalid borrowed metadata must reject through core validation before dependent construction");
    }
}
void missing_metadata_rejects_visual_projection() {
    native_test::SessionCatalogFixture fixture;
    Session session(fixture.physical.world,fixture.physical.frames,false,0,&fixture.catalog);
    const auto& room=native_test::catalog_room(*session.lifecycle(),fixture.catalog.first());
    require(room.banners().empty(),"Null metadata must not fabricate visual state");
    rejects([&] { room.banner_phase(fixture.owners.front().owners.front().identity); },"Visual projection must not silently substitute missing phases");
}
void actual_route(char** argv) {
    const auto mask=read_asset(argv[1],4'000'512),hazards=read_asset(argv[2],8192),frames=read_asset(argv[3],65'536);
    Room physical(parse_mask(mask,checksum(mask)),parse_spikes(hazards,checksum(hazards)));
    const auto bank=parse_player_assets(frames,checksum(frames));
    const auto catalog=parse_room_catalog(read_asset(argv[4],room_catalog_byte_limit));
    const auto owners=parse_authored_decals(read_asset(argv[5],65'536),authored_decal_catalog_checksum,catalog);
    Session session(physical.world,bank.bank,false,1,&catalog,&owners);
    FirstRoomSession expected(physical.world,bank.bank,false,1,&catalog,&owners);
    std::ifstream controls(argv[6]);if(!controls) throw std::runtime_error("Cannot read existing legal controls");
    Controller controller;int tick=0,x=0,y=0,jump=0,dash=0,grab=0,count=0;bool loaded=false;
    while(controls>>tick>>x>>y>>jump>>dash>>grab) {
        if(tick!=count++ || count>3600 || x<-1 || x>1 || y<-1 || y>1 || jump<0 || jump>1 || dash<0 || dash>1 || grab<0 || grab>1)
            throw std::invalid_argument("Invalid existing legal controls");
        Controls raw;raw.left=x<0;raw.right=x>0;raw.up=y<0;raw.down=y>0;raw.cross=jump;raw.square=dash;raw.l=grab;
        const auto sample=controller.sample(raw);session.step(sample);expected.step(1.f/60,sample.player);
        same_configuration_state(*session.lifecycle(),expected);
        if(!loaded && session.lifecycle()->room_definition()==&catalog.definitions()[1]) {
            const auto& room=native_test::catalog_room(*session.lifecycle(),catalog.definitions()[1]);
            require(room.banners().size()==4,"Room load must forward all four actual authored Banners");
            unsigned platforms=0;
            for(const auto& entity:room.entities) if(std::holds_alternative<RoomJumpThru>(entity->object)) {
                ++platforms;
                require(room.jump_thru_visual(entity->object_identity).cells==std::vector<std::pair<int,int>>{{0,0},{1,1},{1,1},{1,0},{2,0}},
                    "Actual metadata must retain Source visual interior rows 1,1,0");
                require(entity->image_cells==std::vector<std::pair<int,int>>{{0,0},{1,0},{1,0},{1,1},{2,0}},"Actual physical interior rows must remain 0,0,1");
            }
            require(platforms==1,"Existing destination must initialize its real authored JumpThru");
            loaded=true;
        }
    }
    require(controls.eof() && count==514 && loaded && !session.lifecycle()->transition(),"Existing route must complete its genuine room transition");
    const auto before=session.lifecycle()->object_identity();
    try { session.step({{},true,false}); }
    catch(const std::runtime_error& error) {
        require(std::string(error.what()).find("Room2 diagnostic reload")!=std::string::npos && session.resets()==0 &&
            session.lifecycle()->object_identity()==before,"Unsupported Room2 reset must preserve its existing guard without reconstruction");
        std::cout<<"constructor integration: 514 existing route samples matched direct core; authored Room2 visual/physical choices and reset guard passed\n";
        return;
    }
    throw std::runtime_error("Room2 diagnostic reset must remain unsupported");
}
}
int main(int argc,char** argv) {
    try {
        if(argc==7) { actual_route(argv);return 0; }
        if(argc!=1) throw std::invalid_argument("Expected optional existing mask hazards frames CROOM1 CDO1 controls");
        initial_construction_forwards_exact_catalog_and_metadata();
        repeated_reset_retains_configuration_parameterized();
        natural_reload_retains_borrowed_visual_metadata();
        null_configuration_preserves_existing_automatic_behavior();
        invalid_metadata_bindings_reject_parameterized();
        missing_metadata_rejects_visual_projection();
        std::cout<<"6 diagnostic session catalog behaviors passed\n";
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
