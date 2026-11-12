#include "particle_commands.hpp"
#include "asset_text.hpp"
#include "lifecycle_fixture.hpp"
#include <functional>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace celeste;
using namespace celeste::particle_commands;
namespace {
void require(bool value,const char* message) { if(!value) throw std::runtime_error(message); }
void rejects(const std::function<void()>& operation) {
    try { operation(); } catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Invalid particle input accepted");
}
std::string catalog_text() {
    std::string text="CDUS1\n"+std::string(64,'a')+'\n'+std::string(64,'b')+"\nDust 4\n";
    for(int index=0;index<4;++index)
        text+=std::to_string(index)+" Synthetic "+std::to_string(index*10)+" 10 5 6 -2 -1 8 8 synthetic/dust"+std::to_string(index)+'\n';
    return text;
}
Catalog catalog() { const auto text=catalog_text();return parse(text,asset_text::checksum(text)); }
draw_order::DrawProjection drawn() {
    draw_order::DrawOwner owner;
    owner.kind=draw_order::OwnerKind::particle_system_mid;
    owner.identity=draw_order::level_particles_identity;owner.sort_depth_band=-8000;
    return {{owner},{0},{}};
}
DustParticle birth() { return {{10,20},{2,-6},1,0.7f,0.4f,1.f,0.f}; }
void add(DustParticles& particles,DustParticle value=birth()) { particles.add(value,DustParticleType::dust); }
void birth_keeps_complete_original_samples() {
    DustParticles particles;const auto value=birth();add(particles,value);
    const auto& particle=particles.slots()[0];
    require(particle.active && particle.generation==1 && particle.start_life==value.life && particle.start_size==value.size,"Missing Dust start state");
    require(particle.birth.position.x==10 && particle.birth.speed.y==-6 && particle.birth.rotation==1 && particle.birth.spin==0 && particle.source==1,"Birth samples changed");
}
void same_frame_age_uses_predecrement_life_ratio() {
    DustParticles particles;add(particles);particles.update(0.125f);
    const auto& particle=particles.slots()[0];
    require(particle.life==birth().life-0.125f && particle.size==0.7f,"First update must retain initial size");
    require(particle.position.x==10.25f && particle.position.y==19.25f && particle.speed.y==-5.5f,"Position must integrate before acceleration");
    require(particle.rotation==1 && particle.birth.position.x==10 && particle.birth.life==0.4f,"Visual age must not rewrite birth observations");
}
void cubic_scale_uses_start_size_not_previous_size() {
    DustParticles particles;auto value=birth();value.life=1;add(particles,value);
    particles.update(0.5f);particles.update(0.125f);
    require(particles.slots()[0].size==value.size*0.875f,"CubeOut uses ratio before subtracting this frame delta");
}
void life_exhaustion_returns_before_motion() {
    DustParticles particles;add(particles);particles.update(0.4f);
    const auto& particle=particles.slots()[0];
    require(!particle.active && particle.life==0 && particle.position.y==20 && particle.speed.y==-6,"Expired Dust must not integrate");
    require(project(drawn(),particles,catalog()).empty(),"Expired Dust still rendered");
}
void negative_position_truncates_towards_zero_and_ignores_trim_for_center() {
    DustParticles particles;auto value=birth();value.position={-1.75f,-0.75f};add(particles,value);
    const auto command=project(drawn(),particles,catalog()).front();
    require(command.position.x==-1 && command.position.y==0,"Particle position must truncate, not floor");
    require(command.origin.x==4 && command.origin.y==4,"Particle center must not apply atlas trim");
    require(command.source_width==5 && command.source_height==6 && command.rotation==1,"Dust material projection changed");
    require(command.color.r==255 && command.color.g==255 && command.color.b==255 && command.color.a==255 && command.effects=="None","Default Dust is static white with no fade/effects");
}
void slot_reuse_draws_in_slot_order_not_birth_order() {
    DustParticles particles;
    for(unsigned index=0;index<DustParticles::capacity;++index) add(particles);
    auto value=birth();value.source=3;add(particles,value);
    const auto commands=project(drawn(),particles,catalog());
    require(commands.size()==400 && commands[0].slot==0 && commands[0].generation==2 && commands[0].texture=="synthetic/dust3","Slot cycling must overwrite exactly slot zero");
    require(commands[1].slot==1 && commands[1].generation==1 && commands.back().slot==399,"Draw must follow slots, not emission order");
}
void clear_preserves_next_slot_and_generations() {
    DustParticles particles;add(particles);particles.clear();add(particles);
    const auto commands=project(drawn(),particles,catalog());
    require(commands.size()==1 && commands.front().slot==1 && particles.slots()[0].generation==1,"Clear must not reset Source nextSlot");
}
void clear_rect_edges_are_exclusive_parameterized() {
    for(const auto at:std::array<Vec2,6>{{{1,1},{0,1},{2,1},{1,0},{1,2},{-1,1}}}) {
        DustParticles particles;auto value=birth();value.position=at;add(particles,value);
        particles.clear_outside(0,0,2,2);
        require(particles.slots()[0].active==(at.x==1 && at.y==1),"Source ClearRect uses strict interior comparisons");
    }
}
void projection_is_observational() {
    DustParticles particles;add(particles);particles.update(0.125f);
    const auto before=particles.slots()[0];project(drawn(),particles,catalog());project(drawn(),particles,catalog());
    const auto& after=particles.slots()[0];
    require(before.life==after.life && before.position.x==after.position.x && before.size==after.size && before.generation==after.generation,"Projection mutated Dust state");
}
void unsupported_type_rejects_before_slot_mutation() {
    DustParticles particles;rejects([&] { particles.add(birth(),static_cast<DustParticleType>(1)); });
    require(particles.slots()[0].generation==0,"Rejected type consumed a slot");
}
void invalid_birth_negatives_parameterized() {
    for(int mutation=0;mutation<7;++mutation) {
        DustParticles particles;auto value=birth();
        if(mutation==0) value.life=0;
        if(mutation==1) value.size=-1;
        if(mutation==2) value.source=4;
        if(mutation==3) value.position.x=std::numeric_limits<float>::quiet_NaN();
        if(mutation==4) value.speed.y=std::numeric_limits<float>::infinity();
        if(mutation==5) value.spin=1;
        if(mutation==6) value.rotation=std::numeric_limits<float>::infinity();
        rejects([&] { add(particles,value); });
        require(particles.slots()[0].generation==0,"Rejected birth changed slot");
    }
}
void owner_negatives_parameterized() {
    for(int mutation=0;mutation<7;++mutation) {
        DustParticles particles;add(particles);auto projection=drawn();
        if(mutation==0) projection.live[0].identity+=1;
        if(mutation==1) projection.live[0].kind=draw_order::OwnerKind::particle_system_back;
        if(mutation==2) projection.live[0].sort_depth_band=8000;
        if(mutation==3) projection.dispatch.push_back(0);
        if(mutation==4) projection.live.push_back(projection.live[0]);
        if(mutation==5) projection.dispatch[0]=1;
        if(mutation==6) projection.live[0].visible=false;
        rejects([&] { project(projection,particles,catalog()); });
    }
}
void invalid_delta_rejects_before_update_parameterized() {
    for(float delta:{-1.f,std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity()}) {
        DustParticles particles;add(particles);rejects([&] { particles.update(delta); });
        require(particles.slots()[0].life==0.4f,"Invalid delta changed lifetime");
    }
}
void invalid_rect_rejects() { DustParticles particles;rejects([&] { particles.clear_outside(2,0,1,2); }); }
void out_of_int_domain_fails_before_render_cast() {
    DustParticles particles;auto value=birth();value.position.x=2147483648.f;add(particles,value);
    rejects([&] { project(drawn(),particles,catalog()); });
}
void catalog_negatives_parameterized() {
    const auto text=catalog_text();
    for(const auto& mutation:std::vector<std::pair<std::string,std::string>>{
        {"CDUS1","CDUS2"},{"Dust 4","Other 4"},{"Dust 4","Dust 3"},{"0 Synthetic","1 Synthetic"},
        {"synthetic/dust1","synthetic/dust0"},{" 5 6 "," 0 6 "},{" 8 8 "," 0 8 "},
        {" -2 -1 "," -4097 -1 "},{"synthetic/dust0","../dust0"},{std::string(64,'a'),std::string(64,'A')}}) {
        auto changed=text;const auto at=changed.find(mutation.first);require(at!=std::string::npos,"Missing catalog mutation");
        changed.replace(at,mutation.first.size(),mutation.second);
        rejects([&] { parse(changed,asset_text::checksum(changed)); });
    }
}
void catalog_trailing_rejects() { const auto text=catalog_text()+"extra\n";rejects([&] { parse(text,asset_text::checksum(text)); }); }
void catalog_truncation_rejects() { auto text=catalog_text();text.pop_back();rejects([&] { parse(text,asset_text::checksum(text)); }); }
void catalog_pin_rejects() { const auto text=catalog_text();rejects([&] { parse(text,asset_text::checksum(text)^1); }); }
void engine_freeze_keeps_visual_dust_unaged() {
    native_test::LifecycleFixture fixture;FirstRoomSession session(fixture.world,fixture.frames);
    for(unsigned tick=0;tick<36;++tick) session.step(1.f/60,{});
    PlayerInput jump;jump.jump={true,true,false};session.step(1.f/60,jump);
    require(session.visual_dust().slots()[0].active,"Actual Player Jump must emit Dust");
    PlayerInput dash;dash.dash_button={true,true,false};dash.aim_x=1;session.step(1.f/60,dash);
    const auto before=session.visual_dust().slots()[0];
    session.step(1.f/60,{});
    require(!session.scene_ran() && session.visual_dust().slots()[0].life==before.life,"Engine freeze must not age Dust");
}
void committed_corpse_does_not_stop_level_particles() {
    native_test::LifecycleFixture fixture;
    fixture.spikes.back()=StaticSpike({29,128},16,SpikeDirection::left);
    FirstRoomSession session(fixture.world,fixture.frames);
    for(unsigned tick=0;tick<36;++tick) session.step(1.f/60,{});
    PlayerInput jump;jump.jump={true,true,false};session.step(1.f/60,jump);
    PlayerInput dash;dash.dash_button={true,true,false};dash.aim_x=1;session.step(1.f/60,dash);
    for(unsigned tick=0;!session.pending_corpse() && tick<20;++tick) session.step(1.f/60,{});
    require(session.pending_corpse() && session.visual_dust().slots()[0].active,"Synthetic side spike must kill Player while Dust remains alive");
    float before=0;
    for(unsigned tick=0;!session.committed_corpse() && tick<10;++tick) {
        before=session.visual_dust().slots()[0].life;session.step(1.f/60,{});
    }
    require(session.committed_corpse() && session.visual_dust().slots()[0].life==before-1.f/60,"Level particles must keep updating on corpse scene frames");
}
void nonzero_wind_branch_remains_unsupported() {
    RoomWind wind;wind.speed.x=1;
    try { wind.update(1.f/60); }
    catch(const std::runtime_error& error) {
        require(std::string(error.what()).find("nonzero wind")!=std::string::npos,"Wrong wind branch rejection");return;
    }
    throw std::runtime_error("Unproved wind emission/RNG branch must remain rejected");
}
void zero_x_acceleration_still_applies_source_float_addition() {
    DustParticles particles;auto value=birth();value.speed.x=-0.f;add(particles,value);particles.update(0.1f);
    require(!std::signbit(particles.slots()[0].speed.x),"Source Vector2 acceleration adds positive zero to X");
}
}
int main() {
    unsigned count=0;
    for(const auto test:{birth_keeps_complete_original_samples,same_frame_age_uses_predecrement_life_ratio,
        cubic_scale_uses_start_size_not_previous_size,life_exhaustion_returns_before_motion,
        negative_position_truncates_towards_zero_and_ignores_trim_for_center,slot_reuse_draws_in_slot_order_not_birth_order,
        clear_preserves_next_slot_and_generations,clear_rect_edges_are_exclusive_parameterized,projection_is_observational,
        unsupported_type_rejects_before_slot_mutation,invalid_birth_negatives_parameterized,owner_negatives_parameterized,
        invalid_delta_rejects_before_update_parameterized,invalid_rect_rejects,out_of_int_domain_fails_before_render_cast,
        catalog_negatives_parameterized,catalog_trailing_rejects,catalog_truncation_rejects,catalog_pin_rejects,
        engine_freeze_keeps_visual_dust_unaged,committed_corpse_does_not_stop_level_particles,
        nonzero_wind_branch_remains_unsupported,zero_x_acceleration_still_applies_source_float_addition}) {
        try { test();++count; } catch(const std::exception& error) { std::cerr<<"behavior "<<count<<": "<<error.what()<<'\n';return 1; }
    }
    std::cout<<count<<" particle behaviors passed\n";
}
