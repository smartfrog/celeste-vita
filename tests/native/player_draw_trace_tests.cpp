#include "player_draw_trace.hpp"
#include "lifecycle_fixture.hpp"
#include <iostream>
#include <sstream>

using namespace celeste;
namespace {
void require(bool condition, const char* message) {
    if(!condition) throw std::runtime_error(message);
}
std::vector<native_test::LogicalPlayerFrame> mapping(const PlayerFrameBank& bank) {
    std::vector<native_test::LogicalPlayerFrame> result;
    for(const auto& frame:bank.frames) result.push_back({"syntheticSheet",512,512,16,32,frame.width,frame.height});
    return result;
}
std::string write(const FirstRoomSession& session, const PlayerFrameBank& bank, const std::vector<PlayerDraw>& cached) {
    std::ostringstream stream;
    native_test::write_player_draw(stream,0,session.player().object_identity(),std::string(session.phase())=="live",bank,mapping(bank),cached);
    return stream.str();
}
void cached_export_is_repeatable_and_does_not_mutate_following_updates() {
    native_test::LifecycleFixture fixture;
    FirstRoomSession observed(fixture.world,fixture.frames),control(fixture.world,fixture.frames);
    for(int tick=0;tick<80;++tick) {
        observed.step(1.f/60,{});control.step(1.f/60,{});
        const auto cached=observed.draw();const auto expected=control.draw();
        const auto pose=observed.presentation().pose();
        const auto words=observed.random().state_words();const auto calls=observed.random().calls();
        const auto first=write(observed,fixture.frames,cached);
        require(first==write(observed,fixture.frames,cached),"Repeated cached export must be byte-identical");
        const auto& after=observed.presentation().pose();const auto& next=control.presentation().pose();
        require(observed.random().state_words()==words && observed.random().calls()==calls,"Export must not consume RNG");
        require(after.animation==pose.animation && after.timer==pose.timer && after.callback_hash==pose.callback_hash &&
            after.sprite_color.r==pose.sprite_color.r && after.wave==pose.wave,"Export must not advance presentation");
        for(unsigned node=0;node<4;++node) require(after.hair_nodes[node].x==pose.hair_nodes[node].x && after.hair_nodes[node].y==pose.hair_nodes[node].y &&
            after.hair_nodes[node].x==next.hair_nodes[node].x && after.hair_nodes[node].y==next.hair_nodes[node].y,"Export must not floor hair again or alter following updates");
        require(cached.size()==expected.size(),"Observed/control real render counts must agree");
        for(unsigned i=0;i<cached.size();++i) require(cached[i].position.x==expected[i].position.x && cached[i].position.y==expected[i].position.y &&
            cached[i].frame==expected[i].frame && cached[i].scale.x==expected[i].scale.x && cached[i].scale.y==expected[i].scale.y,
            "Observation must leave the next real command list unchanged");
        require(observed.player().actor().body.position.x==control.player().actor().body.position.x &&
            observed.player().actor().body.position.y==control.player().actor().body.position.y && observed.context().clock.frame_counter==control.context().clock.frame_counter,
            "Observer must not advance simulation");
    }
}
void mapping_tampering_is_rejected_parameterized() {
    native_test::LifecycleFixture fixture;
    for(const char* text:{"invalid 0", "CPLAYERDRAW1 1", "CPLAYERDRAW1 999"}) {
        std::istringstream stream(text);
        try { native_test::read_player_draw_mapping(stream,fixture.frames); }
        catch(const std::invalid_argument&) { continue; }
        throw std::runtime_error("Invalid logical mapping accepted");
    }
}
void mapping_alias_trim_uv_tampering_is_rejected_parameterized() {
    native_test::LifecycleFixture fixture;
    std::ostringstream text;
    text<<"CPLAYERDRAW1 "<<fixture.frames.frames.size()<<'\n';
    for(const auto& frame:fixture.frames.frames)
        text<<frame.name<<' '<<frame.page<<' '<<frame.u<<' '<<frame.v<<' '<<frame.width<<' '<<frame.height<<' '
            <<frame.trim_x<<' '<<frame.trim_y<<' '<<frame.frame_width<<' '<<frame.frame_height
            <<" syntheticSheet 512 512 16 32 "<<frame.width<<' '<<frame.height<<'\n';
    std::istringstream valid(text.str());
    require(native_test::read_player_draw_mapping(valid,fixture.frames).size()==fixture.frames.frames.size(),"Valid mapping must cover every native frame");
    for(int mutation=0;mutation<3;++mutation) {
        auto bank=fixture.frames;
        if(mutation==0) bank.frames[0].name="other";
        if(mutation==1) ++bank.frames[0].trim_x;
        if(mutation==2) ++bank.frames[0].u;
        std::istringstream stream(text.str());
        try { native_test::read_player_draw_mapping(stream,bank); }
        catch(const std::invalid_argument&) { continue; }
        throw std::runtime_error("Mapping alias/trim/physical UV tampering accepted");
    }
}
void nonfinite_cached_command_fails_before_output() {
    native_test::LifecycleFixture fixture;
    FirstRoomSession session(fixture.world,fixture.frames);
    auto cached=session.draw();cached[0].position.x=std::numeric_limits<float>::quiet_NaN();
    std::ostringstream stream;
    try { native_test::write_player_draw(stream,0,session.player().object_identity(),false,fixture.frames,mapping(fixture.frames),cached); }
    catch(const std::invalid_argument&) {
        require(stream.str().empty(),"Invalid cached commands must fail before publishing a partial block");
        return;
    }
    throw std::runtime_error("Nonfinite cached command accepted");
}
}
int main() {
    try {
        cached_export_is_repeatable_and_does_not_mutate_following_updates();
        mapping_tampering_is_rejected_parameterized();
        mapping_alias_trim_uv_tampering_is_rejected_parameterized();
        nonfinite_cached_command_fails_before_output();
        std::cout<<"4 cached Player draw behaviors passed\n";
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
