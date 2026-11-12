#include "assets.hpp"
#include "lifecycle_fixture.hpp"
#include "draw.hpp"
#include "fixture_io.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace celeste;

namespace {
void require(bool condition,const char* message) {
    if(!condition) throw std::runtime_error(message);
}
PlayerFrameBank sweat_bank() {
    auto bank=native_test::lifecycle_bank();
    const auto add=[&](const char* id,float delay,const char* next,unsigned count) {
        PlayerAnimation animation{std::string("player_sweat_")+id,delay,next,{}};
        for(unsigned i=0;i<count;++i) {
            animation.frames.push_back(unsigned(bank.frames.size()));
            bank.frames.push_back({std::string("sweat/")+id+std::to_string(i),0,1,1,5,4,12,15,32,32,{},0,false});
        }
        bank.animations.push_back(std::move(animation));
    };
    add("idle",0,"player_sweat_idle",1);
    add("climb",0.1f,"player_sweat_climbLoop",2);
    add("climbLoop",0.1f,"player_sweat_climbLoop",6);
    add("still",0.1f,"player_sweat_still",2);
    add("jump",0.1f,"player_sweat_idle",3);
    add("danger",0.05f,"player_sweat_danger",2);
    return bank;
}
void extended_bank_is_accepted() {
    auto bank=sweat_bank();
    bank.validate();
    require(bank.animations.size()==33,"Sweat must extend rather than replace the body bank");
}
PlayerProjection climbing() {
    PlayerProjection p;
    p.state=1;
    p.position={10,50};
    p.solid_point=p.solid_body=p.jump_thru_body=[](Vec2){return false;};
    return p;
}
void idle_zero_delay_does_not_advance() {
    auto bank=sweat_bank();auto p=climbing();PlayerPresentation view(bank,p.position);
    view.observe(PlayerCosmeticPhase::components,p,1);
    require(view.sweat_pose().animation=="player_sweat_idle" && !view.sweat_pose().animating && view.sweat_pose().timer==0,
            "Source's missing idle delay must remain zero, not .1");
}
void still_to_climb_selects_frame_zero_after_component_advance() {
    auto bank=sweat_bank();auto p=climbing();PlayerPresentation view(bank,p.position);
    view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
    view.observe(PlayerCosmeticPhase::components,p,0.1f);
    require(view.sweat_pose().animation=="player_sweat_still" && view.sweat_pose().animation_frame==1,"Fixture must advance still before selection");
    p.climb_move=-1;
    view.observe(PlayerCosmeticPhase::sweat_climb,p,0.1f);
    require(view.sweat_pose().animation=="player_sweat_climb" && view.sweat_pose().animation_frame==0 && view.sweat_pose().timer==0,
            "Newly selected climb frame zero must be visible on the selection tick");
}
void repeated_selection_does_not_restart_climb() {
    auto bank=sweat_bank();auto p=climbing();p.climb_move=-1;PlayerPresentation view(bank,p.position);
    view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
    view.observe(PlayerCosmeticPhase::components,p,0.06f);
    const auto before=view.sweat_pose();
    view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
    require(view.sweat_pose().timer==before.timer && view.sweat_pose().callback_hash==before.callback_hash,
            "Sprite.Play defaults to restart false");
}
void climb_intro_goes_to_loop_and_selector_preserves_it() {
    auto bank=sweat_bank();auto p=climbing();p.climb_move=-1;PlayerPresentation view(bank,p.position);
    view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
    view.observe(PlayerCosmeticPhase::components,p,0.1f);
    require(view.sweat_pose().animation_frame==1,"Climb must play its second intro frame");
    view.observe(PlayerCosmeticPhase::components,p,0.1f);
    require(view.sweat_pose().animation=="player_sweat_climbLoop" && view.sweat_pose().animation_frame==0,"Climb must goto loop frame 2");
    for(unsigned frame=1;frame<=6;++frame) {
        view.observe(PlayerCosmeticPhase::components,p,0.1f);
        const auto before=view.sweat_pose();
        view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
        require(view.sweat_pose().animation=="player_sweat_climbLoop" && view.sweat_pose().animation_frame==frame%6 &&
                view.sweat_pose().timer==before.timer && view.sweat_pose().callback_hash==before.callback_hash,
                "ClimbUpdate must preserve the active frames 2-7 loop, not replay climb");
    }
}
void float_residual_is_retained_across_goto() {
    auto bank=sweat_bank();auto p=climbing();p.climb_move=-1;PlayerPresentation view(bank,p.position);
    view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
    view.observe(PlayerCosmeticPhase::components,p,0.25f);
    require(view.sweat_pose().animation_frame==1 && view.sweat_pose().timer==0.25f-0.1f,"A large delta advances only one frame with residual");
    view.observe(PlayerCosmeticPhase::components,p,0);
    require(view.sweat_pose().animation=="player_sweat_climbLoop" && view.sweat_pose().timer==(0.25f-0.1f)-0.1f,
            "Goto must retain Source float residual rather than reset a six-tick table");
}
void non_upward_selector_parameterized() {
    for(int move:{0,1}) for(bool ground:{false,true}) for(float timer:{0.f,0.01f}) {
        auto bank=sweat_bank();auto p=climbing();p.climb_move=move;p.on_ground=ground;p.climb_no_move_timer=timer;
        PlayerPresentation view(bank,p.position);
        view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
        require(view.sweat_pose().animation==(timer<=0 && !ground ? "player_sweat_still" : "player_sweat_idle"),
                "Airborne down/still chooses still; grounded and positive no-move timer choose idle");
    }
}
void danger_override_parameterized() {
    for(int move:{-1,0,1}) for(bool ground:{false,true}) for(float timer:{0.f,0.01f}) for(float stamina:{20.f,20.001f}) {
        auto bank=sweat_bank();auto p=climbing();p.climb_move=move;p.on_ground=ground;p.climb_no_move_timer=timer;p.stamina=stamina;
        PlayerPresentation view(bank,p.position);
        view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
        require((view.sweat_pose().animation=="player_sweat_danger")== (stamina<=20),"Danger threshold is inclusive in every selector branch");
    }
}
void danger_uses_point_zero_five_delay() {
    auto bank=sweat_bank();auto p=climbing();p.stamina=20;PlayerPresentation view(bank,p.position);
    view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
    view.observe(PlayerCosmeticPhase::components,p,0.025f);
    require(view.sweat_pose().animation_frame==0,"Danger must not advance before .05");
    view.observe(PlayerCosmeticPhase::components,p,0.025f);
    require(view.sweat_pose().animation_frame==1 && view.sweat_pose().timer==0,"Danger advances at exactly .05 using float accumulation");
}
void climb_end_preserves_jump() {
    auto bank=sweat_bank();auto p=climbing();PlayerPresentation view(bank,p.position);
    view.observe(PlayerCosmeticPhase::sweat_jump,p,0);
    view.observe(PlayerCosmeticPhase::components,p,0.05f);
    view.observe(PlayerCosmeticPhase::sweat_end,p,0);
    require(view.sweat_pose().animation=="player_sweat_jump" && view.sweat_pose().timer==0.05f,"ClimbEnd must preserve an active jump");
}
void climb_end_resets_non_jump_to_idle() {
    auto bank=sweat_bank();auto p=climbing();PlayerPresentation view(bank,p.position);
    view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
    view.observe(PlayerCosmeticPhase::sweat_end,p,0);
    require(view.sweat_pose().animation=="player_sweat_idle" && view.sweat_pose().timer==0,"ClimbEnd resets non-jump animations");
}
void jump_restarts_and_then_goes_to_idle() {
    auto bank=sweat_bank();auto p=climbing();PlayerPresentation view(bank,p.position);
    view.observe(PlayerCosmeticPhase::sweat_jump,p,0);
    view.observe(PlayerCosmeticPhase::components,p,0.1f);
    view.observe(PlayerCosmeticPhase::sweat_jump,p,0);
    require(view.sweat_pose().animation_frame==0 && view.sweat_pose().timer==0,"Every new jump explicitly restarts the active jump");
    for(int i=0;i<3;++i) view.observe(PlayerCosmeticPhase::components,p,0.1f);
    require(view.sweat_pose().animation=="player_sweat_idle" && view.sweat_pose().animation_frame==0,"Jump must goto idle");
}
void natural_climb_jump_preserves_source_event_order() {
    auto bank=sweat_bank();Body wall{{4,-100},Hitbox{8,300,{}},true};PlayerWorld world;world.collision.solids={&wall};
    Player player(world,{0,50});PlayerPresentation view(bank,{0,50});PlayerInput input;input.grab=true;
    const auto observe=[&](PlayerCosmeticPhase phase){view.observe(phase,project_player(player,world,input),player.clock().delta);};
    player.frame(1.f/60,input,{},observe);
    require(player.state_machine().state()==1,"Fixture must naturally enter climb");
    input.jump={true,true,false};
    player.frame(1.f/60,input,{},observe);
    require(player.state_machine().state()==0 && player.state().stamina==110.f-27.5f && view.sweat_pose().animation=="player_sweat_jump",
            "ClimbJump must select jump after stamina deduction and before ClimbEnd");
}
void natural_wall_boost_refund_animation_parameterized() {
    for(bool refund:{false,true}) {
        auto bank=sweat_bank();Body wall{{4,-100},Hitbox{8,300,{}},true};PlayerWorld world;world.collision.solids={&wall};
        Player player(world,{0,50});PlayerPresentation view(bank,{0,50});PlayerInput input;input.grab=true;
        bool awaiting_refund=false,refunded_before_components=false;
        const auto observe=[&](PlayerCosmeticPhase phase) {
            if(awaiting_refund && phase==PlayerCosmeticPhase::components && player.state().wall_boost_timer==0 && player.state().stamina==110) {
                require(view.sweat_pose().animation=="player_sweat_idle" && view.sweat_pose().timer==0,
                        "Wall-boost refund must select idle before component animation advances");
                refunded_before_components=true;
            }
            view.observe(phase,project_player(player,world,input),player.clock().delta);
        };
        player.frame(1.f/60,input,{},observe);
        require(player.state_machine().state()==1,"Fixture must naturally enter climb before jumping");
        input.jump={true,true,false};
        player.frame(1.f/60,input,{},observe);
        require(player.state_machine().state()==0 && player.state().wall_boost_timer>0 && player.state().stamina==82.5f &&
                view.sweat_pose().animation=="player_sweat_jump","Natural stationary ClimbJump and ClimbEnd must preserve jump");
        input.grab=false;input.jump={false,false,true};input.x=refund?-1:0;
        awaiting_refund=refund;
        unsigned updates=0;
        while(player.state().wall_boost_timer>0 && updates++<30) {
            player.frame(1.f/60,input,{},observe);
            input.jump={};
        }
        require(player.state().wall_boost_timer<=0,"Natural wall-boost window must end without an unbounded test loop");
        if(refund) {
            require(refunded_before_components && player.state().stamina==110 && view.sweat_pose().animation=="player_sweat_idle",
                    "Steering away must cancel jump on the refund update, not after the animation finishes");
        } else {
            require(player.state().stamina==82.5f && view.sweat_pose().animation=="player_sweat_jump",
                    "Expiry without a refund must preserve the still-active jump animation");
        }
        std::cout<<"natural wall-boost refund="<<refund<<" updates="<<updates<<" stamina="<<player.state().stamina
                 <<" timer="<<player.state().wall_boost_timer<<" sweat="<<view.sweat_pose().animation<<'\n';
    }
}
void natural_stamina_deduction_selects_danger_on_the_same_update() {
    auto bank=sweat_bank();Body wall{{4,-10000},Hitbox{8,20000,{}},true};PlayerWorld world;world.collision.solids={&wall};
    Player player(world,{0,50});PlayerPresentation view(bank,{0,50});PlayerInput input;input.grab=true;input.y=-1;
    float before=110;
    for(unsigned tick=0;tick<180 && player.state().stamina>20;++tick) {
        before=player.state().stamina;
        player.frame(1.f/60,input,{},[&](PlayerCosmeticPhase phase) {
            const auto p=project_player(player,world,input);
            require(p.stamina==player.state().stamina && p.climb_no_move_timer==player.state().climb_no_move_timer,
                    "Sweat projection must expose the unchanged gameplay values");
            view.observe(phase,p,player.clock().delta);
        });
    }
    require(before>20 && player.state().stamina<=20 && player.state_machine().state()==1 && view.sweat_pose().animation=="player_sweat_danger",
            "The threshold-crossing deduction must choose danger immediately, not one tick later");
}
void selected_frame_owns_trimmed_origin() {
    auto bank=sweat_bank();auto p=climbing();PlayerPresentation view(bank,p.position);
    view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
    const auto still=view.sweat_draw(p);const auto& frame=bank.frames[still.frame];
    require(still.origin.x-frame.trim_x==4 && still.origin.y-frame.trim_y==17,"Still origin follows Source frame trim");
    p.climb_move=-1;
    auto& climb=bank.frames[bank.animation("player_sweat_climb").frames[0]];climb.width=climb.height=1;climb.trim_x=10;climb.trim_y=18;
    view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
    const auto draw=view.sweat_draw(p);const auto vertices=diagnostic::player_vertices(climb,draw);
    require(draw.origin.x-climb.trim_x==6 && draw.origin.y-climb.trim_y==14 && vertices[0].x==p.position.x-6 && vertices[0].y==p.position.y-14,
            "Climb origin changes only through its own selected metadata");
}
void non_idle_sweat_keeps_previous_horizontal_sign() {
    auto bank=sweat_bank();auto p=climbing();p.facing=-1;PlayerPresentation view(bank,p.position);
    view.sweat_draw(p);
    view.observe(PlayerCosmeticPhase::sweat_climb,p,0);
    p.facing=1;
    require(view.sweat_draw(p).scale.x==-1,"Non-idle Sweat preserves its previous scale sign, not current Facing");
}
void sweat_does_not_change_body_hair_or_random() {
    auto bank=sweat_bank();auto legacy=native_test::lifecycle_bank();auto p=climbing();
    PlayerPresentation view(bank,p.position),control(legacy,p.position);
    for(int i=0;i<300;++i) {
        for(auto phase:{PlayerCosmeticPhase::scene_tick,PlayerCosmeticPhase::components,PlayerCosmeticPhase::after_update}) {
            view.observe(phase,p,1.f/60);control.observe(phase,p,1.f/60);
        }
        p.climb_move=-1;p.stamina=i<200?110:20;
        view.observe(PlayerCosmeticPhase::sweat_climb,p,1.f/60);
    }
    const auto a=view.draw(p),b=control.draw(p);
    require(a.size()==b.size() && a.size()==21 && view.pose().callback_hash==control.pose().callback_hash && view.random_calls()==control.random_calls(),
            "Sweat animation must not change Body callbacks, command count/order or RNG");
    for(unsigned i=0;i<a.size();++i)
        require(a[i].frame==b[i].frame && a[i].position.x==b[i].position.x && a[i].position.y==b[i].position.y &&
                a[i].origin.x==b[i].origin.x && a[i].origin.y==b[i].origin.y && a[i].scale.x==b[i].scale.x && a[i].scale.y==b[i].scale.y,
                "Body and Hair poses/order must remain unchanged");
}
void lifecycle_visibility_retains_sweat_after_body_only_when_live() {
    native_test::LifecycleFixture fixture;fixture.frames=sweat_bank();FirstRoomSession session(fixture.world,fixture.frames);
    const auto effect=session.draw();
    require(effect.size()==40,"Respawn14 must render only its death effect, not Sweat");
    for(int i=0;i<36;++i) session.step(1.f/60,{});
    const auto draws=session.draw();
    require(draws.size()==22 && draws.back().frame==session.presentation().sweat_pose().frame && draws[20].frame==session.presentation().pose().frame,
            "Visible live Player must retain Hair, Body, Sweat component order");
}
std::string metadata(const PlayerFrameBank& bank) {
    std::ostringstream text;
    text<<"CSPP1\nfd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe\nace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab\n1\n00000000\n"<<bank.frames.size()<<'\n';
    for(const auto& f:bank.frames) text<<f.name<<" 0 1 1 "<<f.width<<' '<<f.height<<' '<<f.trim_x<<' '<<f.trim_y<<" 32 32 0 0 0 "<<f.has_hair<<'\n';
    text<<bank.animations.size()<<'\n';
    for(const auto& a:bank.animations) {
        text<<a.id<<' '<<native_test::bits(a.delay)<<' '<<(a.next.empty()?"-":a.next)<<' '<<a.frames.size();
        for(auto f:a.frames) text<<' '<<f;
        text<<'\n';
    }
    text<<"0 0 0 0\n";
    return text.str();
}
void legacy_and_extended_metadata_parameterized() {
    for(unsigned count:{24,27,30,33}) {
        auto bank=sweat_bank();
        if(count==24 || count==27) bank.animations.resize(count);
        else if(count==30) bank.animations.erase(bank.animations.begin()+24,bank.animations.begin()+27);
        bank.validate();
        const auto text=metadata(bank);const auto assets=diagnostic::parse_player_assets(text,diagnostic::checksum(text));
        require(assets.bank.animations.size()==count,"Core and Vita parser must accept legacy24/27 and extended30/33 without dropping animations");
    }
}
template<class F> void rejects(F run) {
    try {run();} catch(const std::invalid_argument&) {return;}
    throw std::runtime_error("Malformed sweat metadata must fail loudly");
}
void malformed_metadata_parameterized() {
    for(int mutation=0;mutation<5;++mutation) {
        auto bank=sweat_bank();
        switch(mutation) {
        case 0:bank.animations.back().id="unknown";break;
        case 1:bank.animations.back().next="missing";break;
        case 2:bank.animations.back().frames={999};break;
        case 3:bank.animations.back().delay=-1;break;
        case 4:bank.animations.back().id=bank.animations[27].id;break;
        }
        rejects([&]{bank.validate();});
        const auto text=metadata(bank);
        rejects([&]{diagnostic::parse_player_assets(text,diagnostic::checksum(text));});
    }
}
void unknown_animation_fails_before_pose_mutation() {
    auto bank=sweat_bank();auto p=climbing();PlayerPresentation view(bank,p.position);const auto before=view.pose();
    rejects([&]{view.play_animation("player_sweat_unknown");});
    require(view.pose().callback_hash==before.callback_hash,"Unknown animation must fail before mutating Body");
}
void nonfinite_sweat_projection_is_rejected() {
    auto bank=sweat_bank();auto p=climbing();PlayerPresentation view(bank,p.position);
    p.stamina=std::numeric_limits<float>::quiet_NaN();
    rejects([&]{view.observe(PlayerCosmeticPhase::sweat_climb,p,0);});
    require(view.sweat_pose().animation=="player_sweat_idle","Bad projection must fail before selecting Sweat");
}
}

int main() {
    try {
        extended_bank_is_accepted();
        idle_zero_delay_does_not_advance();still_to_climb_selects_frame_zero_after_component_advance();
        repeated_selection_does_not_restart_climb();climb_intro_goes_to_loop_and_selector_preserves_it();
        float_residual_is_retained_across_goto();non_upward_selector_parameterized();danger_override_parameterized();
        danger_uses_point_zero_five_delay();climb_end_preserves_jump();climb_end_resets_non_jump_to_idle();
        jump_restarts_and_then_goes_to_idle();natural_climb_jump_preserves_source_event_order();selected_frame_owns_trimmed_origin();
        natural_wall_boost_refund_animation_parameterized();
        natural_stamina_deduction_selects_danger_on_the_same_update();
        non_idle_sweat_keeps_previous_horizontal_sign();sweat_does_not_change_body_hair_or_random();
        lifecycle_visibility_retains_sweat_after_body_only_when_live();legacy_and_extended_metadata_parameterized();
        malformed_metadata_parameterized();unknown_animation_fails_before_pose_mutation();nonfinite_sweat_projection_is_rejected();
        std::cout<<"23 sweat behaviors passed\n";
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n'; return 1; }
}
