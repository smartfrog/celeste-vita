#include "terrain.hpp"
#include "asset_text.hpp"
#include "terrain_draw_trace.hpp"
#include "lifecycle_fixture.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <sstream>
#include <vector>

using namespace celeste;
namespace {
void expect(bool value,const char* message) { if(!value) throw std::runtime_error(message); }
template<class Action> void rejects(Action action) {
    try { action(); } catch(const std::invalid_argument&) { return; }
    throw std::runtime_error("Expected invalid terrain rejection");
}
std::string fixture() {
    std::string text="CSTV1\n";
    for(int i=0;i<4;++i) text+=std::string(64,'a')+'\n';
    return text+"-16 -16 8 6 8 1\n1\nsyntheticSheet 64 64\n2\n"
        "synthetic/a 0 0 0 8 8 0 0 8 8 255 255 255 255 1\n"
        "synthetic/b 0 8 0 8 8 0 0 8 8 255 255 255 255 1\n"
        "2\nB 10000 4\n0 0 0\n1 1 1\n1 2 0\n7 5 1\nF -10000 1\n2 2 1\n";
}
terrain::Catalog parse(const std::string& text) { return terrain::parse(text,asset_text::checksum(text)); }
std::vector<terrain::Command> commands(const terrain::Catalog& catalog,bool background,Vec2 camera,Vec2 size={8,8}) {
    std::vector<terrain::Command> result;
    catalog.project(background,camera,size,[&](const auto& command) { result.push_back(command); });
    return result;
}
void sparse_order_and_world_coordinates() {
    const auto catalog=parse(fixture());
    const auto result=commands(catalog,true,{-16,-16},{64,48});
    expect(result.size()==4 && result[0].position.x==-16 && result[0].position.y==-16 &&
        result[1].position.x==-8 && result[1].position.y==-8 && result[2].position.y==0 &&
        result[3].position.x==40 && result[3].position.y==24,"Sparse x-outer/y-inner world order");
}
void negative_fraction_and_tile_edges_parameterized() {
    const auto catalog=parse(fixture());
    struct Example { float x; int left,right; };
    for(const auto e:{Example{-0.25f,0,4},{0,1,4},{7.99f,1,5},{8,2,5},{-16,0,2}}) {
        const auto window=catalog.window({e.x,0},{8,8});
        expect(window.left==e.left && window.right==e.right,"Floor camera then origin-relative floor/ceil plus extension");
    }
}
void layers_are_separate() {
    const auto catalog=parse(fixture());
    const auto result=commands(catalog,false,{0,0});
    expect(result.size()==1 && result[0].material==1 && result[0].position.x==0 && result[0].position.y==0,"Independent foreground layer");
}
void partial_edges_keep_full_quads() {
    const auto catalog=parse(fixture());
    const auto result=commands(catalog,true,{-9,-9});
    expect(result.size()==3 && result.front().position.x==-16 && catalog.materials()[0].width==8,"No room scissor or partial edge trimming");
}
void filler_survives_camera_move() {
    const auto catalog=parse(fixture());
    const auto result=commands(catalog,true,{40,24});
    expect(result.size()==1 && result[0].position.x==40 && result[0].position.y==24,"Global filler retained outside first window");
}
void outside_bounds_parameterized() {
    const auto catalog=parse(fixture());
    for(const auto camera:{Vec2{-100,-100},{100,100}}) {
        const auto window=catalog.window(camera,{8,8});
        expect(window.outside_catalog && commands(catalog,true,camera).empty(),"Explicit outside condition and safe empty clamp");
    }
}
void invalid_camera_parameterized() {
    const auto catalog=parse(fixture());
    for(int mode=0;mode<4;++mode) rejects([&] {
        catalog.window(mode==0?Vec2{std::numeric_limits<float>::quiet_NaN(),0}:Vec2{},
            mode==1?Vec2{0,8}:mode==2?Vec2{-1,8}:mode==3?Vec2{std::numeric_limits<float>::infinity(),8}:Vec2{8,8});
    });
}
void repeated_projection_is_pure() {
    const auto catalog=parse(fixture());
    const auto first=commands(catalog,true,{-9,-9});
    for(int i=0;i<3;++i) {
        const auto next=commands(catalog,true,{-9,-9});
        expect(next.size()==first.size() && next.back().position.y==first.back().position.y,"Repeated const projection stable");
    }
}
void malformed_catalog_parameterized() {
    const std::vector<std::pair<std::string,std::string>> mutations={
        {"CSTV1","CSTV2"},{std::string(64,'a'),std::string(64,'g')},
        {"8 6 8 1","8 6 4 1"},{"8 6 8 1","8 6 8 2"},{"8 6 8 1","0 6 8 1"},
        {"syntheticSheet 64 64","syntheticSheet 0 64"},{"synthetic/a 0","synthetic/a 1"},
        {"synthetic/a 0 0 0","synthetic/a 0 60 0"},{"255 255 255 255 1","255 255 255 255 0"},
        {"8 8 0 0 8 8","8 8 1 0 8 8"},{"B 10000 4","F 10000 4"},
        {"F -10000 1","B -10000 1"},{"B 10000 4","B 10000 5"},
        {"1 1 1\n1 2 0","1 1 1\n1 1 0"},{"7 5 1","8 5 1"},
        {"2 2 1","2 2 2"},{"0 0 0\n1 1 1","1 1 1\n0 0 0"},
        {"-16 -16","-016 -16"},{"2 2 1\n","2 2 1\nextra\n"},
        {"F -10000 1\n2 2 1\n","F -10000 1\n"}
    };
    for(const auto& mutation:mutations) {
        auto text=fixture();const auto at=text.find(mutation.first);
        expect(at!=std::string::npos,"Mutation precondition");text.replace(at,mutation.first.size(),mutation.second);
        rejects([&] { parse(text); });
    }
}
void checksum_mismatch() { rejects([] { terrain::parse(fixture(),0); }); }
void truncation_at_every_byte_parameterized() {
    const auto text=fixture();
    for(std::size_t size=0;size<text.size();++size) rejects([&] { parse(text.substr(0,size)); });
}
void duplicate_sheet() {
    auto text=fixture();const std::string original="1\nsyntheticSheet 64 64\n";
    text.replace(text.find(original),original.size(),"2\nsyntheticSheet 64 64\nsyntheticSheet 64 64\n");
    rejects([&] { parse(text); });
}
draw_order::DrawProjection owners() {
    return {{{draw_order::OwnerKind::background_tiles,11,-1,nullptr,10000},
             {draw_order::OwnerKind::solid_tiles,12,-1,nullptr,-10000}},{0,1},{}};
}
void observer_does_not_mutate_session_or_render_cadence() {
    const auto catalog=parse(fixture());
    native_test::LifecycleFixture lifecycle;
    FirstRoomSession observed(lifecycle.world,lifecycle.frames),control(lifecycle.world,lifecycle.frames);
    for(int tick=0;tick<80;++tick) {
        observed.step(1.f/60,{});control.step(1.f/60,{});
        std::ostringstream first,second;
        native_test::write_terrain_draw(first,tick,catalog,observed.camera(),owners());
        native_test::write_terrain_draw(second,tick,catalog,observed.camera(),owners());
        expect(first.str()==second.str(),"Repeated terrain observation stable");
        expect(observed.random().state_words()==control.random().state_words() && observed.random().calls()==control.random().calls(),"Terrain observer must not consume RNG");
        const auto actual=observed.draw(),expected=control.draw();
        expect(actual.size()==expected.size(),"One real Player draw per tick unchanged");
        for(unsigned i=0;i<actual.size();++i)
            expect(actual[i].position.x==expected[i].position.x && actual[i].position.y==expected[i].position.y &&
                actual[i].frame==expected[i].frame,"Terrain observation must not change cached Player commands");
        expect(observed.camera().x==control.camera().x && observed.camera().y==control.camera().y &&
            observed.player().actor().body.position.x==control.player().actor().body.position.x &&
            observed.player().actor().body.position.y==control.player().actor().body.position.y &&
            observed.context().clock.frame_counter==control.context().clock.frame_counter,"Terrain observation must not alter subsequent simulation");
    }
}
void invalid_observer_owner_fails_before_output_parameterized() {
    const auto catalog=parse(fixture());
    for(int mode=0;mode<4;++mode) {
        auto roster=owners();
        if(mode==0) roster.live.pop_back();
        if(mode==1) roster.live[0].sort_depth_band=0;
        if(mode==2) roster.dispatch.push_back(0);
        if(mode==3) roster.live[1].identity=roster.live[0].identity;
        std::ostringstream stream;
        rejects([&] { native_test::write_terrain_draw(stream,0,catalog,{},roster); });
        expect(stream.str().empty(),"Invalid owner must fail before output");
    }
}
}
int main() {
    try {
        sparse_order_and_world_coordinates();negative_fraction_and_tile_edges_parameterized();layers_are_separate();
        partial_edges_keep_full_quads();filler_survives_camera_move();outside_bounds_parameterized();
        invalid_camera_parameterized();repeated_projection_is_pure();malformed_catalog_parameterized();checksum_mismatch();
        truncation_at_every_byte_parameterized();duplicate_sheet();
        observer_does_not_mutate_session_or_render_cadence();invalid_observer_owner_fails_before_output_parameterized();
        std::cout<<"14 terrain test groups passed\n";
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
