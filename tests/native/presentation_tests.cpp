#include "presentation.hpp"
#include "draw.hpp"
#include "diagnostic.hpp"
#include "presentation_trace.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>

using namespace celeste;

namespace {
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
PlayerFrameBank bank() {
    PlayerFrameBank b;
    b.pages = 1;
    for (int i=0; i<3; ++i) b.frames.push_back({"synthetic"+std::to_string(i),0,1,1,10,10,0,0,32,32,{float(i),-2},i,true});
    for (const char* id : {"idle","idleA","idleB","idleC","runSlow","runFast","runStumble","flip","skid","jumpSlow","jumpFast","fallSlow","fallFast","duck","edge","edgeBack","push","lookUp","climbUp","climbLookBackStart","climbLookBack","dangling","wallslide","dash"})
        b.animations.push_back({id,0.1f,id,{0,1,2}});
    b.bangs = {0,1,2}; b.hair=0;
    return b;
}
PlayerProjection grounded() {
    PlayerProjection p;
    p.position = {20,160}; p.on_ground = true;
    p.solid_point = [](Vec2 p) {return p.y>=160;};
    p.solid_body = [](Vec2 p) {return p.y>160;};
    p.jump_thru_body = [](Vec2) {return false;};
    return p;
}
void animation_advances_before_selection() {
    auto b=bank(); auto p=grounded(); PlayerPresentation v(b,p.position);
    v.observe(PlayerCosmeticPhase::components,p,0.1f);
    require(v.pose().animation_frame==1,"Source timer must advance before selection");
}
void stopped_non_null_animation_selects_grounded_idle() {
    auto b=bank();auto p=grounded();
    for(auto& animation:b.animations) if(animation.id=="fallSlow") animation.next.clear();
    PlayerPresentation view(b,p.position);
    view.play_animation("fallSlow");
    for(unsigned frame=0;frame<3;++frame) view.observe(PlayerCosmeticPhase::components,p,0.1f);
    require(!view.pose().animating && view.pose().animation.empty(),"Terminal animation must stop with an empty non-null ID");
    view.observe(PlayerCosmeticPhase::select,p,1.f/60);
    require(view.pose().animation=="idle" && view.pose().animation_frame==0,"Grounded selector must recover idle from an empty non-null animation ID");
}
void idle_variants_are_not_restarted_parameterized() {
    for(const char* id:{"idle","idleA","idleB","idleC"}) {
        auto b=bank();auto p=grounded();PlayerPresentation view(b,p.position);
        view.play_animation(id);
        view.observe(PlayerCosmeticPhase::components,p,0.1f);
        const auto before=view.pose();const auto calls=view.random_calls();
        view.observe(PlayerCosmeticPhase::select,p,1.f/60);
        const auto& after=view.pose();
        require(after.animation==id && after.animation_frame==before.animation_frame && after.timer==before.timer &&
            after.callback_hash==before.callback_hash && view.random_calls()==calls,"Grounded selection must preserve an existing idle variant without restarting or consuming RNG");
    }
}
void initialized_presentation_has_a_non_null_idle_id() {
    auto b=bank();auto p=grounded();PlayerPresentation view(b,p.position);
    require(view.pose().animation=="idle","Initialized bounded presentation must publish the bank's valid idle ID");
    const auto callbacks=view.pose().change_callbacks;
    view.observe(PlayerCosmeticPhase::select,p,1.f/60);
    require(view.pose().animation=="idle" && view.pose().change_callbacks==callbacks,"Initial idle must not be restarted by selection");
}
void unsupported_carry_animation_fails_without_pose_mutation() {
    auto b=bank();auto p=grounded();PlayerPresentation view(b,p.position);
    const auto callbacks=view.pose().change_callbacks;
    try { view.play_animation("idle_carry"); }
    catch(const std::invalid_argument&) {
        require(view.pose().animation=="idle" && view.pose().change_callbacks==callbacks,"Unsupported carry animation must fail before changing the bounded pose");
        return;
    }
    throw std::runtime_error("Holding/carry animation is outside the bounded presentation bank");
}
void large_delta_advances_only_once() {
    auto b=bank(); auto p=grounded(); PlayerPresentation v(b,p.position);
    v.observe(PlayerCosmeticPhase::components,p,1.0f);
    require(v.pose().animation_frame==1,"Sprite.Update must not drain a large timer in a loop");
}
void hair_simulates_all_four_nodes() {
    auto b=bank(); auto p=grounded(); PlayerPresentation v(b,p.position);
    v.observe(PlayerCosmeticPhase::components,p,1.f/60);
    v.observe(PlayerCosmeticPhase::after_update,p,1.f/60);
    require(v.pose().hair_nodes[0].y==149,"Hair root uses frame offset and scaled body anchor");
    for (unsigned i=1;i<4;++i) {
        auto a=v.pose().hair_nodes[i-1],n=v.pose().hair_nodes[i];
        require(std::hypot(n.x-a.x,n.y-a.y)<3.00001f,"Hair spring must constrain each segment");
    }
}
void hair_draws_outline_then_reverse_fill_then_body() {
    auto b=bank(); auto p=grounded(); PlayerPresentation v(b,p.position);
    v.observe(PlayerCosmeticPhase::after_update,p,1.f/60);
    auto draws=v.draw(p);
    require(draws.size()==21,"Four outlined hair nodes plus body must all draw");
    require(draws.front().color.r==0 && draws[16].color.r==172,"Hair outlines must precede colored fill");
    require(draws.back().origin.x==16 && draws.back().origin.y==32,"Body must draw last with source origin");
}
void depleted_color_truncates_each_lerp_channel() {
    auto b=bank(); auto p=grounded(); PlayerPresentation v(b,p.position);
    p.dashes=0;
    v.observe(PlayerCosmeticPhase::hair_color,p,1.f/60);
    auto c=v.pose().hair_color;
    require(c.r==161 && c.g==63 && c.b==70,"FNA Color.Lerp must truncate byte channels, not round");
}
void one_choice_goto_does_not_consume_random() {
    auto b=bank(); auto p=grounded(); PlayerPresentation v(b,p.position);
    for(int i=0;i<4;++i)v.observe(PlayerCosmeticPhase::components,p,0.1f);
    require(v.random_calls()==0,"Original Chooser one-choice fast path must retain its zero RNG consumption");
}
void signed_squash_preserves_trim_and_fractional_root() {
    PlayerFrame frame{"synthetic",0,1,1,12,10,6,20,32,32,{},0,true};
    PlayerDraw draw{0,{20.75f,100.25f},{16,32},{-0.6f,1.4f},0,{}};
    auto vertices=celeste::diagnostic::player_vertices(frame,draw);
    require(std::abs(vertices[0].x-26.75f)<0.00001f && std::abs(vertices[0].y-83.45f)<0.00001f,
            "Signed body squash must transform the trim-adjusted source origin without flooring geometry");
    require(vertices[1].x<vertices[0].x,"Negative scale must preserve source winding and UV orientation");
}
void session_skips_positive_freeze_including_zero_crossing() {
    auto b=bank();
    Body floor{{-100,0},Hitbox{200,8,{}},true};
    PlayerWorld world;world.collision.solids={&floor};
    celeste::diagnostic::Session session(world,{},&b);
    celeste::diagnostic::Sample dash;dash.player.dash_button={true,true,false};dash.player.aim_x=1;
    session.step(dash);
    const float wave=session.presentation()->pose().wave;
    require(session.player().clock().freeze_timer>0,"Fixture must enter a real Dash freeze");
    while(session.player().clock().freeze_timer>0) {
        session.step({});
        require(session.presentation()->pose().wave==wave,"Frozen and zero-crossing ticks must not advance hair simulation");
    }
    session.step({});
    require(session.presentation()->pose().wave>wave,"Presentation must resume on the next simulation tick");
}
void natural_climb_hop_clears_fast_jump_before_selection() {
    auto b=bank();
    Body wall{{4,0},Hitbox{8,100,{}},true};
    PlayerWorld world;world.collision.solids={&wall};
    Player player(world,{0,11},{0,160});
    PlayerPresentation view(b,player.actor().body.position);
    PlayerInput input;
    const auto cosmetic=[&](PlayerCosmeticPhase phase) {
        view.observe(phase,project_player(player,world,input),player.clock().delta);
    };
    player.frame(0,input,{},cosmetic);
    require(view.pose().fast_jump,"Falling must establish fastJump before the natural ledge hop");
    input.grab=true;
    player.frame(0,input,{},cosmetic);
    require(player.state_machine().state()==1,"Held Grab must enter Climb on the finite wall");
    input.y=-1;
    unsigned frames=0;
    while(player.state_machine().state()==1 && frames++<120) player.frame(1.f/60,input,{},cosmetic);
    require(player.state_machine().state()==0 && player.state().speed.y==-120,"Climbing past the ledge must naturally call ClimbHop");
    require(!view.pose().fast_jump && view.pose().animation=="jumpSlow","ClimbHop must clear fastJump before animation selection");
}
void climb_hop_event_resets_only_fast_jump_before_selection() {
    auto b=bank();auto p=grounded();p.on_ground=false;p.speed.y=160;
    PlayerPresentation view(b,p.position);
    view.observe(PlayerCosmeticPhase::select,p,1.f/60);
    require(view.pose().fast_jump && view.pose().animation=="fallFast","Falling must establish fastJump for the event test");
    const auto scale=view.pose().scale;
    const auto calls=view.random_calls();
    view.observe(PlayerCosmeticPhase::climb_hop,p,1.f/60);
    require(!view.pose().fast_jump && view.pose().animation=="fallFast","ClimbHop must reset the flag without selecting an animation");
    require(view.pose().scale.x==scale.x && view.pose().scale.y==scale.y && view.random_calls()==calls,"ClimbHop must not squash the sprite or consume random values");
    p.speed.y=-120;
    view.observe(PlayerCosmeticPhase::select,p,1.f/60);
    require(view.pose().animation=="jumpSlow","The next selector must observe the ClimbHop reset");
}
void legacy_projection_rejects_a_meaningful_climb_hop_reset() {
    auto b=bank();auto p=grounded();p.on_ground=false;p.speed.y=160;
    native_test::PresentationTrace trace(b,p.position);
    trace.observe("climb_hop_guard",1,PlayerCosmeticPhase::select,p,1.f/60);
    try {
        trace.observe("climb_hop_guard",1,PlayerCosmeticPhase::climb_hop,p,1.f/60);
    } catch(const std::invalid_argument& error) {
        require(std::string(error.what())=="Legacy presentation projection cannot represent a meaningful ClimbHop reset","Legacy projection must fail at its explicit ClimbHop boundary");
        return;
    }
    throw std::runtime_error("Legacy projection must not omit a meaningful ClimbHop reset");
}
}
int main() {
    try {
        animation_advances_before_selection(); large_delta_advances_only_once(); hair_simulates_all_four_nodes();
        hair_draws_outline_then_reverse_fill_then_body(); depleted_color_truncates_each_lerp_channel();
        one_choice_goto_does_not_consume_random();
        signed_squash_preserves_trim_and_fractional_root();
        session_skips_positive_freeze_including_zero_crossing();
        natural_climb_hop_clears_fast_jump_before_selection();
        climb_hop_event_resets_only_fast_jump_before_selection();
        legacy_projection_rejects_a_meaningful_climb_hop_reset();
        stopped_non_null_animation_selects_grounded_idle();
        idle_variants_are_not_restarted_parameterized();
        initialized_presentation_has_a_non_null_idle_id();
        unsupported_carry_animation_fails_without_pose_mutation();
        std::cout<<"15 presentation behaviors passed\n";
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
