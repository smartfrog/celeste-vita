#include "player.hpp"
#include "presentation.hpp"
#include "trails.hpp"
#include "lifecycle_fixture.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>

using namespace celeste;

namespace {
void require(bool condition, const char* message) {
    if(!condition) throw std::runtime_error(message);
}
void uninterrupted_dash_creates_three_trails() {
    PlayerWorld world;
    world.bounds_left=-1000; world.bounds_right=1000;
    Player player(world,{0,0});
    unsigned trails=0;
    std::vector<unsigned> ticks;
    for(int tick=0;tick<30;++tick) {
        PlayerInput input;
        input.aim_x=1;
        input.dash_button={tick==0,tick==0,false};
        player.frame(1.f/60,input,{},[&](PlayerCosmeticPhase phase) {
            if(phase==PlayerCosmeticPhase::dash_trail) {
                ticks.push_back(tick);
                if(trails==0) require(player.state().dash_trail_timer==0,"Launch hook must precede timer assignment");
                if(trails==1) require(player.state().dash_trail_counter==1,"Timer hook must precede counter decrement");
                if(trails==2) require(!player.state().auto_jump,"Completion hook must precede AutoJump");
                ++trails;
            }
        });
    }
    require(trails==3,"Uninterrupted Dash must create launch, timer and completion trails");
    if(ticks!=std::vector<unsigned>({4,9,15})) {
        std::string actual;for(auto tick:ticks) actual+=std::to_string(tick)+",";
        throw std::runtime_error("Trail timing must retain original coroutine/freeze timing: "+actual);
    }
}
void canceled_dash_has_no_completion_trail() {
    PlayerWorld world;
    Player player(world);
    unsigned trails=0;
    auto observe=[&](PlayerCosmeticPhase phase){if(phase==PlayerCosmeticPhase::dash_trail) ++trails;};
    PlayerInput input;input.dash_button={true,true};input.aim_x=1;
    player.frame(0,input,{},observe);player.frame(0.05f,{}, {},observe);player.frame(0,{}, {},observe);
    player.request_state(0);
    for(int i=0;i<20;++i) player.frame(1.f/60,{}, {},observe);
    require(trails==1,"Canceled coroutine must not manufacture a third trail");
}
void capture_is_live_until_before_render_then_immutable() {
    auto bank=native_test::lifecycle_bank();
    bank.frames.push_back({"later",0,1,1,8,8,0,0,32,32,{},0,true});
    bank.animations.front().frames.push_back(2);
    PlayerProjection p;p.position={19.25f,100.75f};p.facing=-1;
    PlayerPresentation presentation(bank,p.position);
    presentation.observe(PlayerCosmeticPhase::jump,p,0);
    PlayerTrails trails;trails.add(p,presentation.pose());
    unsigned captures=0;
    trails.before_render(presentation,p,[&](unsigned,const auto&){++captures;});
    require(captures==0,"Lazy manager must wait for its first Scene commit");
    trails.update(0.025f);
    p.position={22.5f,98.125f};
    presentation.observe(PlayerCosmeticPhase::components,p,0.1f);
    presentation.observe(PlayerCosmeticPhase::stand,p,0);
    presentation.observe(PlayerCosmeticPhase::after_update,p,0.01f);
    const auto nodes=presentation.pose().hair_nodes;
    trails.before_render(presentation,p,[&](unsigned slot,const auto& draws){
        ++captures;
        const auto& body=draws.back();
        require(slot==0 && draws.size()==21 && body.frame==2,"Capture must use live sprite and hair");
        require(body.scale.x==-0.6f && body.scale.y==1.4f,"Only body scale and anchor are saved at creation");
        require(body.position.x==35.f && body.position.y==29.f,"PlayerSprite must floor the live translated render position, not the creation anchor");
        require(draws[16].position.x==nodes[3].x+12.75f,"Hair must translate before rendering");
    });
    require(presentation.pose().hair_nodes[0].x==std::floor(nodes[0].x+12.75f)-12.75f,
            "Hair floor must occur in atlas coordinates and subtract offset afterward");
    presentation.observe(PlayerCosmeticPhase::components,p,0.1f);
    trails.before_render(presentation,p,[&](unsigned,const auto&){++captures;});
    require(captures==1,"Captured bitmap must never be recaptured from the live sprite");
}
void lifetime_expires_before_increment_and_reuses_in_creation_order() {
    PlayerTrails trails;PlayerProjection p;PlayerPose pose;
    trails.add(p,pose);trails.update(0.75f);
    trails.add(p,pose);trails.update(0.25f);
    require(trails.slots()[0].percent==1.f && !trails.slots()[0].removing,"Equality must survive until next source Update");
    trails.update(0.01f);
    require(trails.slots()[0].removing && trails.count()==2,"Removal must remain deferred through rendering");
    trails.update(0.01f);
    require(trails.add(p,pose)==0,"Pool must reuse the first actually freed slot");
    trails.update(0);
    require(trails.render_order()==std::vector<unsigned>({1,0}),"Equal depth must sort by creation order, not slot number");
}
void exhaustion_drops_without_overwriting_parameterized() {
    for(unsigned excess:{1u,3u}) {
        PlayerTrails trails;PlayerProjection p;PlayerPose pose;
        for(unsigned i=0;i<64;++i) require(trails.add(p,pose)==int(i),"First-free pool allocation changed");
        for(unsigned i=0;i<excess;++i) require(trails.add(p,pose)==-1,"Exhaustion must return null semantics");
        require(trails.count()==64 && trails.slots()[0].order==0 && trails.slots()[63].order==63,"Exhaustion overwrote a live bitmap");
    }
}
void fade_uses_original_color_byte_conversion_parameterized() {
    for(const auto& cell:std::vector<std::pair<float,PresentationColor>>{{0,{51,137,191,191}},{0.5f,{6,17,23,23}},{1,{0,0,0,0}},{1.01f,{0,0,0,0}}}) {
        TrailSnapshot slot;slot.percent=cell.first;
        const auto c=PlayerTrails::faded_color(slot),e=cell.second;
        require(c.r==e.r && c.g==e.g && c.b==e.b && c.a==e.a,"Fade must truncate Color channels after .75*(1-CubeOut(p))");
    }
}
void level_pool_survives_corpse_and_clears_before_reload() {
    native_test::LifecycleFixture f;
    FirstRoomSession session(f.world,f.frames);
    while(session.player().state_machine().state()==14) session.step(1.f/60,{});
    auto* pool=&session.trails();
    PlayerInput input;input.aim_x=1;input.dash_button={true,true};
    session.step(1.f/60,input);
    for(int i=0;session.trails().count()==0 && i<12;++i) session.step(1.f/60,{});
    require(session.trails().count()==1,"Production first-room observer must create the launch trail");
    const float percent=session.trails().slots()[0].percent;
    session.step(1.f/60,{});
    require(session.scene_ran() && session.trails().slots()[0].percent>percent,"Scene ticks must age level-owned trails");
    for(int i=0;!session.pending_corpse() && i<60;++i) { PlayerInput right;right.x=1;session.step(1.f/60,right); }
    require(session.pending_corpse() && &session.trails()==pool && session.trails().count()>0,"Death must retain the pool through component transfer");
    session.step(1.f/60,{});
    const float frozen_percent=session.trails().slots()[0].percent;
    session.step(1.f/60,{});
    require(!session.scene_ran() && session.trails().slots()[0].percent==frozen_percent,"Positive freeze SceneSkip must not age trails");
    while(session.stats().reloads==0) session.step(1.f/60,{});
    require(&session.trails()==pool && session.trails().count()==0 && session.trails().generation()==1,"Reload must clear retained manager before reconstructing Player");
}
}
int main() {
    try {
        uninterrupted_dash_creates_three_trails();canceled_dash_has_no_completion_trail();
        capture_is_live_until_before_render_then_immutable();lifetime_expires_before_increment_and_reuses_in_creation_order();
        exhaustion_drops_without_overwriting_parameterized();fade_uses_original_color_byte_conversion_parameterized();
        level_pool_survives_corpse_and_clears_before_reload();
    }
    catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
