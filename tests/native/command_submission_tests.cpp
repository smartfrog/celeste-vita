#include "command_submission.hpp"
#include "draw.hpp"
#include "gameplay_draw.hpp"
#include "guest_file_fixture.hpp"
#include <vitaGL.h>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <type_traits>

using namespace celeste;
using namespace celeste::command_preflight;
using namespace celeste::command_submission;
namespace {
void require(bool condition,const char* message) {
    if(!condition) throw std::runtime_error(message);
}
std::int32_t bits(float value) {
    std::int32_t result;
    std::memcpy(&result,&value,sizeof(result));
    return result;
}
struct Fixture {
    MaterialTable table;
    std::vector<CommandInput> inputs;
    std::vector<UploadedPage> pages{{7,64,32,101},{9,64,32,202},{11,16,16,303}};
    Fixture() {
        table.pages={{7,64,32},{9,64,32},{11,16,16}};
        for(int page:{7,9}) {
            MaterialBinding binding;
            binding.original={"synthetic/sheet",16,24,16,12,-3,-5,32,32,"synthetic/frame"+std::to_string(page)};
            binding.original_sheet_width=128;
            binding.original_sheet_height=64;
            binding.page=page;
            binding.packed_x=4;binding.packed_y=8;
            binding.packed_width=16;binding.packed_height=12;
            table.bindings.push_back(binding);
        }
        for(int page:{7,9,7}) {
            decal_commands::DecalCommand command;
            command.texture="synthetic/frame"+std::to_string(page);
            command.sheet="synthetic/sheet";
            command.identity=inputs.size()+1;
            command.source_x=20;command.source_y=28;
            command.source_width=8;command.source_height=4;
            command.position={10,20};command.origin={2,3};command.scale={-1,1};
            command.color={23,std::uint8_t(inputs.size()),67,89};
            auto geometry=decal_commands::project_geometry(command,128,64);
            command.effects="FlipHorizontally, FlipVertically";
            std::swap(geometry.vertices[0][3],geometry.vertices[1][3]);
            std::swap(geometry.vertices[2][3],geometry.vertices[3][3]);
            std::swap(geometry.vertices[0][4],geometry.vertices[2][4]);
            std::swap(geometry.vertices[1][4],geometry.vertices[3][4]);
            for(unsigned corner=0;corner<4;++corner) {
                geometry.vertices[corner][0]=bits(corner==0 ? -0.f : float(corner));
                geometry.vertices[corner][2]=bits(corner==0 ? -0.f : float(corner)/8);
            }
            inputs.push_back({command,geometry});
        }
    }
    ReadyFrame ready() const { return std::get<ReadyFrame>(preflight(table,inputs)); }
};
struct Recorder {
    unsigned calls=0;
    Projection projection{};
    std::vector<unsigned> textures;
    std::vector<ReadyCommand> quads;
    Sink sink() {
        return {[&](const Projection& p){++calls;projection=p;},
                [&](unsigned texture,const ReadyCommand& q){++calls;textures.push_back(texture);quads.push_back(q);},
                [&]{++calls;}};
    }
};
template<class Function> void invalid(Function function) {
    try {function();} catch(const std::invalid_argument&) {return;}
    throw std::runtime_error("Expected input validation failure");
}
void ordered_quads_preserve_all_packed_bits_and_colors() {
    Fixture f;const auto frame=f.ready();Recorder recorder;
    submit(frame,f.pages,{},recorder.sink());
    require(recorder.calls==5 && recorder.textures==std::vector<unsigned>{101,202,101},"A-B-A order must not regroup");
    for(unsigned i=0;i<3;++i) {
        const auto& expected=frame.commands()[i];const auto& actual=recorder.quads[i];
        require(actual.geometry.vertices==expected.geometry.vertices,"All XYZ/packed UV bits and corner order must survive");
        const auto a=actual.command.color,b=expected.command.color;
        require(a.r==b.r && a.g==b.g && a.b==b.b && a.a==b.a,"Colors must retain Source order");
        require(actual.command.effects==expected.command.effects,"Flips must not be reapplied");
    }
}
void camera_only_changes_projection_and_uses_existing_letterbox() {
    Fixture f;Recorder recorder;
    submit(f.ready(),f.pages,{{-12.25f,6.5f},960,544},recorder.sink());
    const auto& p=recorder.projection;
    require(p.left==-12.25f && p.right==307.75f && p.top==6.5f && p.bottom==186.5f,"Camera must not round");
    require(p.viewport.x==0 && p.viewport.y==2 && p.viewport.width==960 && p.viewport.height==540,"Reuse integer letterbox");
    require(recorder.quads[0].geometry.vertices[0][0]==bits(-0.f),"Camera must not rewrite world XYZ");
}
void uploaded_pages_resolve_by_id_not_vector_position() {
    Fixture f;Recorder recorder;std::reverse(f.pages.begin(),f.pages.end());
    submit(f.ready(),f.pages,{},recorder.sink());
    require(recorder.textures==std::vector<unsigned>{101,202,101},"Resolve caller handles by Page.id");
}
void invalid_metadata_rejects_whole_set_parameterized() {
    for(unsigned kind=0;kind<7;++kind) {
        Fixture f;Recorder recorder;
        switch(kind) {
        case 0: f.pages.push_back(f.pages[0]);break;
        case 1: f.pages.erase(f.pages.begin()+1);break;
        case 2: f.pages[1].texture=0;break;
        case 3: f.pages[1].width=63;break;
        case 4: f.pages[2].height=0;break;
        case 5: f.pages[2].id=99;break;
        case 6: f.pages[2].texture=0;break;
        }
        invalid([&]{submit(f.ready(),f.pages,{},recorder.sink());});
        require(recorder.calls==0,"Late or unused invalid page must precede every callback");
    }
}
void invalid_camera_or_viewport_rejects_before_callbacks_parameterized() {
    for(const View view:std::vector<View>{
        {{std::numeric_limits<float>::quiet_NaN(),0}},
        {{0,std::numeric_limits<float>::infinity()}},
        {{std::numeric_limits<float>::max(),0}},
        {{0,-std::numeric_limits<float>::max()}},
        {{1e10f,0}},{{0,1e10f}},{{1073741824.f,0}},{{0,536870912.f}},
        {{},0,544},{{},960,0},{{},319,180},{{},961,544},{{},960,545},
        {{},std::numeric_limits<int>::max(),std::numeric_limits<int>::max()}}) {
        Fixture f;Recorder recorder;
        invalid([&]{submit(f.ready(),f.pages,view,recorder.sink());});
        require(recorder.calls==0,"Invalid camera/projection/viewport must cause zero callbacks");
    }
}
void missing_callbacks_reject_before_begin_parameterized() {
    for(unsigned kind=0;kind<3;++kind) {
        Fixture f;Recorder recorder;auto sink=recorder.sink();
        if(kind==0) sink.begin={};
        if(kind==1) sink.quad={};
        if(kind==2) sink.end={};
        invalid([&]{submit(f.ready(),f.pages,{},sink);});
        require(recorder.calls==0,"Validate the complete sink before begin");
    }
}
void empty_ready_frame_validates_then_emits_nothing() {
    Fixture f;f.inputs.clear();Recorder recorder;
    submit(f.ready(),f.pages,{},recorder.sink());
    require(recorder.calls==0,"Empty frame must not change sink state");
}
void empty_ready_frame_without_pages_emits_nothing() {
    const auto frame=std::get<ReadyFrame>(preflight({},{}));Recorder recorder;
    submit(frame,{}, {},recorder.sink());
    require(recorder.calls==0,"Validated empty table and frame need no sink effects");
}
void empty_ready_frame_still_requires_unused_pages() {
    Fixture f;f.inputs.clear();Recorder recorder;f.pages.pop_back();
    invalid([&]{submit(f.ready(),f.pages,{},recorder.sink());});
    require(recorder.calls==0,"Empty frame still validates complete table-page set");
}
void sink_failure_propagates_without_claiming_rollback_parameterized() {
    for(unsigned stage=0;stage<3;++stage) {
        Fixture f;unsigned calls=0;
        const auto fail=[&]{++calls;throw std::runtime_error("sink cause");};
        Sink sink{[&](const Projection&){if(stage==0)fail();},
                  [&](unsigned,const ReadyCommand&){if(stage==1)fail();},
                  [&]{if(stage==2)fail();}};
        bool propagated=false;
        try {submit(f.ready(),f.pages,{},sink);} catch(const std::runtime_error& e) {propagated=std::string(e.what())=="sink cause";}
        require(propagated && calls==1,"Preserve sink failure cause, no retry or cleanup callback");
    }
}
void preflight_failure_never_reaches_submission_parameterized() {
    static_assert(!std::is_default_constructible_v<ReadyFrame>);
    static_assert(!std::is_invocable_v<decltype(submit),const Result&,const std::vector<UploadedPage>&,const View&,const Sink&>);
    for(unsigned kind=0;kind<2;++kind) {
        Fixture f;Recorder recorder;
        if(kind==0) f.inputs.back().command.source_height=0;
        else f.inputs.back().geometry.vertices[3][2]=bits(std::numeric_limits<float>::quiet_NaN());
        const auto result=preflight(f.table,f.inputs);
        if(const auto* frame=std::get_if<ReadyFrame>(&result)) submit(*frame,f.pages,{},recorder.sink());
        require(std::holds_alternative<Failure>(result) && recorder.calls==0,"Bad Source packet must not become a third submission interface");
    }
}
struct Sampling {
    int min=GL_LINEAR,mag=GL_LINEAR,wrap_s=GL_REPEAT,wrap_t=GL_REPEAT;
};
struct TextureUnit {
    bool one_dimensional=false,two_dimensional=false;
    unsigned texture=0,sampler=0,environment=GL_MODULATE;
    std::array<float,4> transform{1,1,0,0};
};
struct SampledTexture {
    unsigned unit,texture,environment;
    Sampling sampling;
    std::array<std::array<std::int32_t,2>,4> uv;
};
struct GLRecorder {
    unsigned calls=0,pending_error=GL_NO_ERROR;
    bool context=true,fail_draw=false;
    unsigned fail_bind_at=0,fail_setup=0;
    std::vector<unsigned> textures,modes,disabled;
    std::vector<std::array<std::int32_t,5>> vertices;
    std::vector<std::array<float,2>> uv0;
    std::vector<std::vector<SampledTexture>> sampled;
    std::array<TextureUnit,2> units;
    std::map<unsigned,Sampling> texture_sampling,samplers;
    unsigned active_unit=0,matrix_mode=GL_MODELVIEW;
    std::vector<std::array<unsigned char,4>> colors;
    std::vector<std::array<int,3>> parameters;
    std::array<int,4> viewport{};
    std::array<double,6> ortho{};
    std::array<unsigned,2> blend{};
    unsigned equation=0;
    float u=0,v=0;
    unsigned allocated=0,uploaded=0,fail_upload_at=0,clears=0,swaps=0;
    std::vector<unsigned> deleted;
} gl;
GLRecorder inherited_texture_state(unsigned second_unit_flags=3) {
    GLRecorder state;
    state.active_unit=1;
    state.units[0].one_dimensional=true;
    state.units[0].two_dimensional=true;
    state.units[0].texture=17;
    state.units[0].sampler=91;
    state.units[0].environment=GL_REPLACE;
    state.units[0].transform={2,3,0.25f,0.5f};
    state.units[1].one_dimensional=second_unit_flags&1;
    state.units[1].two_dimensional=second_unit_flags&2;
    state.units[1].texture=19;
    state.samplers[91]={GL_LINEAR,GL_LINEAR,GL_REPEAT,GL_REPEAT};
    return state;
}
void require_effective_page(unsigned index,unsigned texture,const ReadyCommand& command) {
    require(gl.sampled.at(index).size()==1,"Only unit zero may contribute to a ReadyFrame quad");
    const auto& sample=gl.sampled[index][0];
    require(sample.unit==0 && sample.texture==texture,"Effective sampled page must use UV0 and the resolved handle");
    require(sample.environment==GL_MODULATE,"Effective texture environment must modulate Source color");
    require(sample.sampling.min==GL_NEAREST && sample.sampling.mag==GL_NEAREST &&
            sample.sampling.wrap_s==GL_CLAMP_TO_EDGE && sample.sampling.wrap_t==GL_CLAMP_TO_EDGE,
            "Effective sampling must be nearest/clamp, not an inherited sampler override");
    for(unsigned corner=0;corner<4;++corner)
        require(sample.uv[corner]==std::array<std::int32_t,2>{command.geometry.vertices[corner][3],command.geometry.vertices[corner][4]},
                "Effective UV0 must equal packed UV without inherited texture-matrix transforms");
}
void real_entry_normalizes_inherited_texture_state_parameterized() {
    for(unsigned flags:{1u,2u,3u}) {
        Fixture f;const auto frame=f.ready();gl=inherited_texture_state(flags);
        diagnostic::submit_ready_frame(frame,f.pages,{});
        for(unsigned i=0;i<3;++i) require_effective_page(i,i==1?202:101,frame.commands()[i]);
    }
    std::cout<<"stateful host GL mock: inherited unit1 1D/2D, unit0 linear/repeat sampler and UV transform -> effective unit0 A-B-A nearest/clamp/modulate packed UV0\n";
}
void real_entry_clears_unit_zero_sampler_override() {
    Fixture f;const auto frame=f.ready();gl={};
    gl.units[0].sampler=91;
    gl.samplers[91]={GL_LINEAR,GL_LINEAR,GL_REPEAT,GL_REPEAT};
    diagnostic::submit_ready_frame(frame,f.pages,{});
    require_effective_page(0,101,frame.commands()[0]);
}
void real_entry_removes_inherited_texture_matrix_transform() {
    Fixture f;const auto frame=f.ready();gl={};gl.units[0].transform={2,3,0.25f,0.5f};
    diagnostic::submit_ready_frame(frame,f.pages,{});
    require_effective_page(0,101,frame.commands()[0]);
}
void real_entry_rejects_invalid_inputs_before_any_GL_call_parameterized() {
    for(unsigned kind=0;kind<6;++kind) {
        Fixture f;View view;gl=inherited_texture_state();
        if(kind==0) f.pages[1].texture=0;
        if(kind==1) f.pages.push_back(f.pages[0]);
        if(kind==2) f.pages.pop_back();
        if(kind==3) f.pages[1].height=1;
        if(kind==4) view.camera.x=std::numeric_limits<float>::max();
        if(kind==5) view.width=961;
        invalid([&]{diagnostic::submit_ready_frame(f.ready(),f.pages,view);});
        require(gl.calls==0,"Validation failure must precede every real-entry GL call, even context queries");
    }
}
void real_entry_emits_source_order_with_three_dimensional_vertices() {
    Fixture f;const auto frame=f.ready();gl=inherited_texture_state();
    diagnostic::submit_ready_frame(frame,f.pages,{{-12.25f,6.5f}});
    require(gl.textures==std::vector<unsigned>{101,202,101},"Physical sink must preserve A-B-A order");
    require(gl.modes==std::vector<unsigned>(3,GL_TRIANGLE_STRIP),"Source TL/TR/BL/BR corner order requires strips, not GL_QUADS");
    for(unsigned i=0;i<3;++i) for(unsigned corner=0;corner<4;++corner)
        require(gl.vertices[i*4+corner]==frame.commands()[i].geometry.vertices[corner],"Physical sink must bit-cast all XYZ/UV words without recomputation");
    for(unsigned i=0;i<3;++i) {
        const auto c=frame.commands()[i].command.color;
        require(gl.colors[i]==std::array<unsigned char,4>{c.r,c.g,c.b,c.a},"Physical color changes retain Source order");
    }
    require(gl.ortho==std::array<double,6>{-12.25,307.75,186.5,6.5,-1,1},"World camera belongs only in projection");
    require(gl.viewport==std::array<int,4>{0,2,960,540},"Use existing letterbox in physical entry");
    require(gl.blend==std::array<unsigned,2>{GL_ONE,GL_ONE_MINUS_SRC_ALPHA} && gl.equation==GL_FUNC_ADD,"PMA source-over");
    require(std::count(gl.disabled.begin(),gl.disabled.end(),GL_CULL_FACE)==1 &&
            std::count(gl.disabled.begin(),gl.disabled.end(),GL_DEPTH_TEST)==1,"Source quads must not gain culling or depth test");
    for(unsigned i=0;i<3;++i) {
        const auto offset=i*4;
        require(gl.parameters[offset]==std::array<int,3>{GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST} &&
                gl.parameters[offset+1]==std::array<int,3>{GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST} &&
                gl.parameters[offset+2]==std::array<int,3>{GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE} &&
                gl.parameters[offset+3]==std::array<int,3>{GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE},"Nearest/clamp for every submitted handle");
    }
    std::cout<<"host GL mock: A-B-A, 12 XYZUV bit-exact vertices, 3 colors, fractional camera, letterbox, PMA/nearest/clamp\n";
}
void real_entry_empty_frame_has_no_GL_side_effects() {
    Fixture f;f.inputs.clear();gl=inherited_texture_state();
    diagnostic::submit_ready_frame(f.ready(),f.pages,{});
    require(gl.calls==0,"Empty valid frame does not query or change GL");
}
void real_entry_propagates_context_or_driver_cause_parameterized() {
    for(unsigned kind=0;kind<4;++kind) {
        Fixture f;gl={};
        if(kind==0) gl.context=false;
        if(kind==1) gl.pending_error=GL_INVALID_ENUM;
        if(kind==2) gl.fail_draw=true;
        if(kind==3) gl.fail_bind_at=1;
        std::string error;
        try {diagnostic::submit_ready_frame(f.ready(),f.pages,{});} catch(const std::runtime_error& e) {error=e.what();}
        require(error.find("ReadyFrame")!=std::string::npos,"Failure must retain submission context");
        if(kind==0) require(error.find("context")!=std::string::npos && gl.vertices.empty(),"Missing context stops drawing");
        else require(error.find("GL error "+std::to_string(GL_INVALID_ENUM))!=std::string::npos,"Preserve actual GL error code");
        if(kind==2) require(gl.vertices.size()==4 && gl.textures.size()==1,"Stop after actual driver failure; do not claim rollback");
        if(kind==3) require(gl.vertices.empty(),"Texture-state driver failure must stop before vertices");
    }
}
void real_entry_stops_before_vertices_on_texture_unit_setup_error_parameterized() {
    for(unsigned stage:{1u,2u,3u,4u}) {
        Fixture f;gl=inherited_texture_state();gl.fail_setup=stage;
        std::string error;
        try {diagnostic::submit_ready_frame(f.ready(),f.pages,{});} catch(const std::runtime_error& e) {error=e.what();}
        require(error=="ReadyFrame texture unit state: GL error "+std::to_string(GL_INVALID_ENUM),"Preserve the failing texture setup stage and driver code");
        require(gl.vertices.empty() && gl.textures.empty(),"Failed unit setup must stop before page binding or any vertices");
    }
}
void real_fractional_source_camera_is_accepted_and_unchanged() {
    Fixture f;const auto frame=f.ready();gl=inherited_texture_state();
    const float camera=196.91904f;
    diagnostic::submit_ready_frame(frame,f.pages,{{camera,-4.5f}});
    require(gl.textures==std::vector<unsigned>{101,202,101},"Fractional camera must still emit A-B-A order");
    require(gl.ortho[0]==double(camera) && gl.ortho[1]==double(camera+320.f),
            "Preserve the exact Source camera float and its native float extent");
    require(std::fabs((gl.ortho[1]-gl.ortho[0])-320.0)<=320.0*std::numeric_limits<float>::epsilon(),
            "Fractional endpoint span must stay within one float-epsilon of 320");
    for(unsigned i=0;i<3;++i) for(unsigned corner=0;corner<4;++corner)
        require(gl.vertices[i*4+corner]==frame.commands()[i].geometry.vertices[corner],
                "Accepting a fractional camera must not alter packed XYZ/UV bits");
}
void gameplay_draw_success_clears_and_swaps_exactly_once() {
    Fixture f;const auto frame=f.ready();gl=inherited_texture_state();guest_test::reset();
    const auto receipt=diagnostic::draw_gameplay(frame,f.pages,{{196.91904f,-4.5f}},nullptr,17);
    require(receipt.empty() && gl.clears==1 && gl.swaps==1,"Valid no-export success must clear and swap exactly once");
    require(gl.textures==std::vector<unsigned>{101,202,101},"Gameplay draw must preserve deferred A-B-A page order");
    require(gl.ortho[0]==double(196.91904f) && gl.ortho[1]==double(196.91904f+320.f),
            "Gameplay draw must emit the unchanged fractional Source camera");
    for(unsigned i=0;i<3;++i) for(unsigned corner=0;corner<4;++corner)
        require(gl.vertices[i*4+corner]==frame.commands()[i].geometry.vertices[corner],
                "Gameplay success must emit all packed XYZ/UV bits unchanged");
    for(unsigned i=0;i<3;++i) require_effective_page(i,i==1?202:101,frame.commands()[i]);
}
void gameplay_draw_success_exports_only_after_valid_preflight() {
    Fixture f;const auto frame=f.ready();gl={};guest_test::reset();
    const auto receipt=diagnostic::draw_gameplay(frame,f.pages,{{196.91904f,-4.5f}},"gameplay-success.ppm",18);
    require(gl.clears==1 && gl.swaps==1 && receipt.find("frame_saved ")!=std::string::npos,
            "Valid export must clear, submit, read, write and swap once");
    require(guest_test::stored.count("gameplay-success.ppm")==1 && guest_test::stored.count("gameplay-success.ppm.txt")==1,
            "Valid export must write the image and receipt exactly once");
    const auto& image=guest_test::stored.at("gameplay-success.ppm").data;
    require(image.rfind("P6\n960 544\n255\n",0)==0 && image.size()==15+960*544*3,
            "Export must be the bounded 960x544 P6 image");
    require(receipt.find("camera=196.919")!=std::string::npos && receipt.find("pixel_parity_claim=0")!=std::string::npos,
            "Receipt must retain the actual fractional Source camera and avoid parity claims");
}
void gameplay_draw_invalid_input_has_zero_clear_swap_submit_parameterized() {
    for(unsigned kind=0;kind<3;++kind) {
        Fixture f;const auto frame=f.ready();gl=inherited_texture_state();guest_test::reset();
        View view{{196.91904f,-4.5f},960,544};
        auto pages=f.pages;
        if(kind==0) view.camera.x=std::numeric_limits<float>::quiet_NaN();
        if(kind==1) pages.pop_back();
        if(kind==2) view.width=961;
        bool rejected=false;
        try {diagnostic::draw_gameplay(frame,pages,view,nullptr,0);} catch(const std::invalid_argument&) {rejected=true;}
        require(rejected,"Invalid gameplay draw input must reject");
        require(gl.clears==0 && gl.swaps==0 && gl.textures.empty() && gl.vertices.empty() && gl.ortho[0]==0,
                "Failure before the sink must cause zero clear/swap/submit/GL state");
        require(guest_test::stored.empty(),"Failure must not write an export");
    }
}
void real_entry_stops_before_vertices_of_late_failing_page() {
    Fixture f;gl=inherited_texture_state();gl.fail_bind_at=2;
    std::string error;
    try {diagnostic::submit_ready_frame(f.ready(),f.pages,{});} catch(const std::runtime_error& e) {error=e.what();}
    require(error=="ReadyFrame texture and color state: GL error "+std::to_string(GL_INVALID_ENUM),"Retain late page setup error cause");
    require(gl.vertices.size()==4 && gl.textures==std::vector<unsigned>{101,202},"No vertices of the failing second quad or later A quad may be emitted");
}
void production_late_preflight_failure_has_zero_GL_calls() {
    Fixture f;gl={};
    f.inputs.back().command.source_height=0;
    std::string failure;
    try {
        const auto ready=gameplay_bridge::prepare(77,f.table,f.inputs);
        diagnostic::submit_ready_frame(ready,f.pages,{});
    } catch(const std::runtime_error& error) { failure=error.what(); }
    require(gl.calls==0 && failure.find("frame=77")!=std::string::npos && failure.find("empty_crop")!=std::string::npos,
        "Production late failure must precede all physical emitter GL calls");
}
void production_upload_driver_failure_releases_all_owned_handles() {
    gl={};gl.fail_upload_at=2;
    gameplay_bridge::PageOwner owner;
    std::string failure;
    try { diagnostic::upload_gameplay_pages(owner,{{{31,1,1},"aaaa"},{{7,1,1},"bbbb"}}); }
    catch(const std::runtime_error& error) { failure=error.what(); }
    require(failure.find("bounded RGBA texture upload: GL error")!=std::string::npos,
        "Preserve actual upload stage and GL error code");
    require(gl.deleted==std::vector<unsigned>{401,402} && owner.pages().empty(),
        "Physical upload failure must delete earlier and failing allocations");
    diagnostic::dispose_gameplay_pages(owner);
    require(gl.deleted.size()==2,"Physical cleanup must not double-free");
}
void production_upload_owns_generic_page_ids_and_dimensions() {
    gl={};gameplay_bridge::PageOwner owner;
    diagnostic::upload_gameplay_pages(owner,{{{31,1,1},"aaaa"},{{7,2,1},"bbbbbbbb"}});
    require(owner.pages().size()==2 && owner.pages()[0].id==31 && owner.pages()[1].width==2,
        "Page ownership must not alias legacy room or player arrays");
    diagnostic::dispose_gameplay_pages(owner);
    require(gl.deleted==std::vector<unsigned>{401,402},"Dispose all generic page IDs exactly once");
}
void production_upload_invalid_late_page_has_zero_GL_calls() {
    gl={};gameplay_bridge::PageOwner owner;
    invalid([&] { diagnostic::upload_gameplay_pages(owner,{{{31,1,1},"aaaa"},{{7,1,2},"short"}}); });
    require(gl.calls==0,"Validate every actual page byte count before allocating any GL texture");
}
}
extern "C" {
void glGenTextures(int count,GLuint* textures) {++gl.calls;for(int i=0;i<count;++i) textures[i]=401+gl.allocated++;}
void glDeleteTextures(int count,const GLuint* textures) {++gl.calls;for(int i=0;i<count;++i) gl.deleted.push_back(textures[i]);}
void glTexImage2D(unsigned,int,int,int,int,int,unsigned,unsigned,const void*) {
    ++gl.calls;
    if(++gl.uploaded==gl.fail_upload_at) gl.pending_error=GL_INVALID_ENUM;
}
void glClear(unsigned) {++gl.calls;++gl.clears;}
void glClearColor(float,float,float,float) {++gl.calls;}
void glReadBuffer(unsigned) {++gl.calls;}
void glFinish() {++gl.calls;}
void glReadPixels(int,int,int,int,unsigned,unsigned,void*) {++gl.calls;}
void vglSwapBuffers(int) {++gl.calls;++gl.swaps;}
unsigned glGetError() {++gl.calls;const auto error=gl.pending_error;gl.pending_error=GL_NO_ERROR;return error;}
const unsigned char* glGetString(unsigned) {++gl.calls;return gl.context ? reinterpret_cast<const unsigned char*>("mock") : nullptr;}
void glViewport(int x,int y,int w,int h) {++gl.calls;gl.viewport={x,y,w,h};}
void glMatrixMode(unsigned mode) {++gl.calls;gl.matrix_mode=mode;}
void glLoadIdentity() {
    ++gl.calls;
    if(gl.matrix_mode==GL_TEXTURE) {
        if(gl.fail_setup==3) {gl.pending_error=GL_INVALID_ENUM;return;}
        gl.units[gl.active_unit].transform={1,1,0,0};
    }
}
void glOrtho(double l,double r,double b,double t,double n,double f) {++gl.calls;gl.ortho={l,r,b,t,n,f};}
void glDisable(unsigned value) {
    ++gl.calls;gl.disabled.push_back(value);
    if(gl.fail_setup==4 && gl.active_unit==1 && value==GL_TEXTURE_1D) {gl.pending_error=GL_INVALID_ENUM;return;}
    if(value==GL_TEXTURE_1D) gl.units[gl.active_unit].one_dimensional=false;
    if(value==GL_TEXTURE_2D) gl.units[gl.active_unit].two_dimensional=false;
}
void glEnable(unsigned value) {
    ++gl.calls;
    if(value==GL_TEXTURE_1D) gl.units[gl.active_unit].one_dimensional=true;
    if(value==GL_TEXTURE_2D) gl.units[gl.active_unit].two_dimensional=true;
}
void glBlendFunc(unsigned a,unsigned b) {++gl.calls;gl.blend={a,b};}
void glBlendEquation(unsigned equation) {++gl.calls;gl.equation=equation;}
void glTexEnvi(unsigned,unsigned,int environment) {++gl.calls;gl.units[gl.active_unit].environment=environment;}
void glActiveTexture(unsigned texture) {
    ++gl.calls;
    if(gl.fail_setup==1 && texture==GL_TEXTURE0) {gl.pending_error=GL_INVALID_ENUM;return;}
    require(texture==GL_TEXTURE0 || texture==GL_TEXTURE1,"Pinned immediate-mode mock has two texture units");
    gl.active_unit=texture-GL_TEXTURE0;
}
void glBindSampler(unsigned unit,unsigned sampler) {
    ++gl.calls;
    if(gl.fail_setup==2) {gl.pending_error=GL_INVALID_ENUM;return;}
    gl.units.at(unit).sampler=sampler;
}
void glBindTexture(unsigned,unsigned texture) {
    ++gl.calls;gl.textures.push_back(texture);
    if(gl.fail_bind_at==gl.textures.size()) {gl.pending_error=GL_INVALID_ENUM;return;}
    gl.units[gl.active_unit].texture=texture;
}
void glTexParameteri(unsigned a,unsigned b,int c) {
    ++gl.calls;gl.parameters.push_back({int(a),int(b),c});
    auto& sampling=gl.texture_sampling[gl.units[gl.active_unit].texture];
    if(b==GL_TEXTURE_MIN_FILTER) sampling.min=c;
    if(b==GL_TEXTURE_MAG_FILTER) sampling.mag=c;
    if(b==GL_TEXTURE_WRAP_S) sampling.wrap_s=c;
    if(b==GL_TEXTURE_WRAP_T) sampling.wrap_t=c;
}
void glColor4ub(unsigned char r,unsigned char g,unsigned char b,unsigned char a) {++gl.calls;gl.colors.push_back({r,g,b,a});}
void glBegin(unsigned mode) {++gl.calls;gl.modes.push_back(mode);}
void glTexCoord2f(float u,float v) {++gl.calls;gl.u=u;gl.v=v;}
void glVertex3f(float x,float y,float z) {
    ++gl.calls;gl.vertices.push_back({bits(x),bits(y),bits(z),bits(gl.u),bits(gl.v)});gl.uv0.push_back({gl.u,gl.v});
}
void glEnd() {
    ++gl.calls;
    std::vector<SampledTexture> sampled;
    for(unsigned index=0;index<gl.units.size();++index) {
        const auto& unit=gl.units[index];
        if(!unit.one_dimensional && !unit.two_dimensional) continue;
        auto sampling=gl.texture_sampling[unit.texture];
        if(unit.sampler) {
            const auto& sampler=gl.samplers.at(unit.sampler);
            sampling.min=sampler.min;sampling.wrap_s=sampler.wrap_s;sampling.wrap_t=sampler.wrap_t;
        }
        SampledTexture texture{index,unit.texture,unit.environment,sampling,{}};
        for(unsigned corner=0;corner<4;++corner) {
            const auto uv=index==0 ? gl.uv0[gl.uv0.size()-4+corner] : std::array<float,2>{0.875f,0.75f};
            texture.uv[corner]={bits(uv[0]*unit.transform[0]+unit.transform[2]),bits(uv[1]*unit.transform[1]+unit.transform[3])};
        }
        sampled.push_back(texture);
    }
    gl.sampled.push_back(std::move(sampled));
    if(gl.fail_draw)gl.pending_error=GL_INVALID_ENUM;
}
}
int main() {
    try {
        const std::array tests{ordered_quads_preserve_all_packed_bits_and_colors,
            camera_only_changes_projection_and_uses_existing_letterbox,
            uploaded_pages_resolve_by_id_not_vector_position,
            invalid_metadata_rejects_whole_set_parameterized,
            invalid_camera_or_viewport_rejects_before_callbacks_parameterized,
            missing_callbacks_reject_before_begin_parameterized,
            empty_ready_frame_validates_then_emits_nothing,
            empty_ready_frame_without_pages_emits_nothing,
            empty_ready_frame_still_requires_unused_pages,
            sink_failure_propagates_without_claiming_rollback_parameterized,
            preflight_failure_never_reaches_submission_parameterized,
            real_entry_normalizes_inherited_texture_state_parameterized,
            real_entry_clears_unit_zero_sampler_override,
            real_entry_removes_inherited_texture_matrix_transform,
            real_entry_rejects_invalid_inputs_before_any_GL_call_parameterized,
            real_entry_emits_source_order_with_three_dimensional_vertices,
            real_entry_empty_frame_has_no_GL_side_effects,
            real_entry_propagates_context_or_driver_cause_parameterized,
            real_entry_stops_before_vertices_on_texture_unit_setup_error_parameterized,
            real_entry_stops_before_vertices_of_late_failing_page,
            production_late_preflight_failure_has_zero_GL_calls,
            production_upload_driver_failure_releases_all_owned_handles,
            production_upload_owns_generic_page_ids_and_dimensions,
            production_upload_invalid_late_page_has_zero_GL_calls,
            real_fractional_source_camera_is_accepted_and_unchanged,
            gameplay_draw_success_clears_and_swaps_exactly_once,
            gameplay_draw_success_exports_only_after_valid_preflight,
            gameplay_draw_invalid_input_has_zero_clear_swap_submit_parameterized};
        for(auto test:tests) test();
        std::cout<<tests.size()<<" command submission scenarios passed (including parameterized cases)\n";
        return 0;
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
