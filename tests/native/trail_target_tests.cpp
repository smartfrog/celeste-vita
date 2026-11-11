#include "trail_target.hpp"
#include "lifecycle_fixture.hpp"
#include <vitaGL.h>
#include <algorithm>
#include <array>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>

using namespace celeste;
using namespace celeste::diagnostic;

namespace {
std::map<unsigned,int> values;
std::set<unsigned> enabled;
std::array<int,4> viewport{7,9,300,200},scissor{11,12,13,14};
std::array<float,4> color{0.1f,0.2f,0.3f,0.4f};
std::array<float,4> clear_color{0.6f,0.3f,0.2f,0.8f};
using Matrix=std::array<float,16>;
struct MatrixState {
    Matrix current{};
    std::vector<Matrix> stack;
    unsigned depth=1;
    bool operator==(const MatrixState& other) const {
        return current==other.current && depth==other.depth && stack.size()==other.stack.size() &&
            std::equal(stack.begin(),stack.begin()+depth,other.stack.begin());
    }
};
std::map<unsigned,MatrixState> matrices;
unsigned pushes=0,pops=0,overflows=0;
std::vector<std::array<int,4>> scissors;
std::vector<std::pair<unsigned,unsigned>> blends;
std::vector<std::array<float,2>> uv;
unsigned allocations=0,deletions=0,draws=0;
unsigned reads=0;
std::vector<std::vector<std::uint8_t>> readbacks;
std::set<unsigned> retained_reads;
std::vector<unsigned> read_formats;
std::vector<bool> marker_scissors;
bool markers_started=false,rgb_error=false,pack_error=false,restore_error=false;
bool matrix_query_error=false,matrix_restore_error=false,matrix_restore_corrupt=false;
unsigned pending_error=GL_NO_ERROR;
bool incomplete=false;
void require(bool value,const char* message) { if(!value) throw std::runtime_error(message); }
struct Snapshot {
    decltype(values) integers=values;
    decltype(enabled) capabilities=enabled;
    decltype(viewport) view=viewport,clip=scissor;
    decltype(color) tint=color;
    decltype(clear_color) clear=clear_color;
    decltype(matrices) stacks=matrices;
    void unchanged() const {
        require(integers==values && capabilities==enabled && view==viewport && clip==scissor && tint==color && clear==clear_color && stacks==matrices,
                "Trail pass leaked GL state");
    }
};
void reset() {
    values={{GL_FRAMEBUFFER_BINDING,31},{GL_READ_FRAMEBUFFER_BINDING,32},{GL_TEXTURE_BINDING_2D,33},{GL_MATRIX_MODE,GL_PROJECTION},
        {GL_BLEND_SRC_RGB,101},{GL_BLEND_DST_RGB,102},{GL_BLEND_SRC_ALPHA,103},{GL_BLEND_DST_ALPHA,104},
        {GL_BLEND_EQUATION_RGB,105},{GL_BLEND_EQUATION_ALPHA,106},{GL_PACK_ALIGNMENT,1}};
    enabled={GL_BLEND,GL_SCISSOR_TEST,GL_CULL_FACE,GL_DEPTH_TEST};
    matrices.clear();
    for(auto mode:{GL_MODELVIEW,GL_PROJECTION}) {
        MatrixState state;state.stack.resize(mode==GL_PROJECTION ? 2 : 32);
        for(unsigned i=0;i<16;++i) state.current[i]=float(mode==GL_PROJECTION ? 5 : 9)+float(i)/8.f;
        matrices.emplace(mode,std::move(state));
    }
    pushes=pops=overflows=0;
    scissors.clear();blends.clear();uv.clear();allocations=deletions=draws=0;incomplete=false;
    reads=0;readbacks.clear();
    retained_reads.clear();read_formats.clear();marker_scissors.clear();markers_started=rgb_error=pack_error=restore_error=false;pending_error=GL_NO_ERROR;
    matrix_query_error=matrix_restore_error=matrix_restore_corrupt=false;
}
void capture_masks_completed_tile_and_restores_state() {
    reset();
    auto bank=native_test::lifecycle_bank();PlayerProjection p;p.position={19,144};
    PlayerPresentation presentation(bank,p.position);PlayerTrails trails;trails.add(p,presentation.pose());trails.update(0);
    TrailTarget target;Snapshot state;
    target.capture(trails,presentation,p,[](unsigned,const auto& commands) {
        require(commands.size()==21,"Capture must submit hair then body");
        require(values[GL_BLEND_SRC_RGB]==GL_ONE && values[GL_BLEND_DST_RGB]==GL_ONE_MINUS_SRC_ALPHA,
                "Hair/body union must use premultiplied source-over");
    });
    state.unchanged();
    require(allocations==1 && draws==2,"Exactly one FBO and clear/mask quad per tile");
    require(blends==std::vector<std::pair<unsigned,unsigned>>({{GL_ONE,GL_ZERO},{GL_ONE,GL_ONE_MINUS_SRC_ALPHA},{GL_DST_ALPHA,GL_ZERO}}),
            "Original MaxBlend is destination alpha/zero, not GL_MAX");
    require(scissors.front()==std::array<int,4>{0,448,64,64},"Atlas capture must clip only the pending tile");
    target.capture(trails,presentation,p,[](unsigned,const auto&){throw std::runtime_error("Recaptured immutable tile");});
    require(allocations==1 && draws==2,"Repeated render must preserve captured tiles without new allocation");
    state.unchanged();target.dispose();require(deletions==1,"Level target teardown must release FBO");
}
void tile_reuse_clears_only_reused_tile() {
    reset();auto bank=native_test::lifecycle_bank();PlayerProjection p;PlayerPresentation presentation(bank,{});
    PlayerTrails trails;TrailTarget target;
    trails.add(p,presentation.pose());trails.update(0);
    target.capture(trails,presentation,p,[](unsigned,const auto&){});
    trails.add(p,presentation.pose());
    target.capture(trails,presentation,p,[](unsigned,const auto&){});
    require(scissors[2]==std::array<int,4>{64,448,64,64} && allocations==1,"Second tile must preserve first tile/FBO");
    require(trails.slots()[0].drawn && trails.slots()[1].drawn,"Both immutable bitmaps must remain resident");
    target.dispose();
}
void target_uv_and_fade_are_applied_once_per_snapshot() {
    reset();auto bank=native_test::lifecycle_bank();PlayerProjection p;PlayerPresentation presentation(bank,{});
    PlayerTrails trails;TrailTarget target;trails.add(p,presentation.pose());trails.update(0.5f);
    target.capture(trails,presentation,p,[](unsigned,const auto&){});
    const unsigned before=draws;target.render(trails);
    require(draws==before+1 && uv==std::vector<std::array<float,2>>({{0,1},{0.125f,1},{0.125f,0.875f},{0,0.875f}}),
            "Completed tile must render as one quad with FBO-oriented UVs");
    target.dispose();
}
void incomplete_target_fails_without_committing_bitmap() {
    reset();incomplete=true;auto bank=native_test::lifecycle_bank();PlayerProjection p;PlayerPresentation presentation(bank,{});
    PlayerTrails trails;trails.add(p,presentation.pose());trails.update(0);TrailTarget target;Snapshot state;
    try { target.capture(trails,presentation,p,[](unsigned,const auto&){}); }
    catch(const std::runtime_error&) {state.unchanged();require(!trails.slots()[0].drawn,"Failed FBO must not commit capture");target.dispose();return;}
    throw std::runtime_error("Incomplete FBO was accepted");
}
void attachment_readback_restores_independent_read_write_targets() {
    reset();auto bank=native_test::lifecycle_bank();PlayerProjection p;PlayerPresentation presentation(bank,{});
    PlayerTrails trails;trails.add(p,presentation.pose());trails.update(0);TrailTarget target;
    target.capture(trails,presentation,p,[](unsigned,const auto&){});Snapshot state;
    require(target.read_rgba().size()==512*512*4,"GPU probe must read actual RGBA attachment");
    state.unchanged();target.dispose();
}
struct ProbeFixture {
    PlayerFrameBank bank=native_test::lifecycle_bank();
    PlayerProjection player;
    PlayerPresentation presentation{bank,{}};
    PlayerTrails trails;
    TrailTarget target;
    ProbeFixture() {
        reset();trails.add(player,presentation.pose());trails.update(0);
        target.capture(trails,presentation,player,[](unsigned,const auto&){});
    }
};
void diagnostic_precedes_swatch_failure_with_untouched_bytes() {
    ProbeFixture fixture;auto& target=fixture.target;auto& trails=fixture.trails;
    std::vector<std::uint8_t> pixels(512*512*4);
    for(unsigned i=0;i<pixels.size();++i) pixels[i]=std::uint8_t(i*37u+11u);
    for(const auto& point:std::vector<std::array<unsigned,3>>{{462,454,192},{486,454,255},{486,470,64}})
        for(unsigned c=0;c<4;++c) pixels[((511-point[1])*512+point[0])*4+c]=std::uint8_t(point[2]);
    readbacks={pixels,pixels};Snapshot state;std::vector<std::uint8_t> diagnostic;std::string receipt;
    try {receipt=target.prepare_probe(trails,[&](const auto& after) {diagnostic=after;});}
    catch(const std::runtime_error& error) {
        require(std::string(error.what())=="GPU trail alpha/orientation swatch failed at 454,454","Original swatch fatal must remain unchanged");
        require(reads==2 && diagnostic==pixels,"Exact after-read bytes must be available before swatch failure, without another read pass");
        require(receipt.empty(),"Failed swatches must not return a normal export receipt");
        state.unchanged();target.dispose();require(deletions==1,"Failed probe must retain disposable target ownership");return;
    }
    throw std::runtime_error("Invalid stub swatches were accepted");
}
void diagnostic_precedes_tile_preservation_failure() {
    ProbeFixture fixture;auto& target=fixture.target;auto& trails=fixture.trails;Snapshot state;
    std::vector<std::uint8_t> before(1048576),after=before;after[448*512*4]=7;readbacks={before,after};
    std::vector<std::uint8_t> diagnostic;std::string receipt;
    try {receipt=target.prepare_probe(trails,[&](const auto& pixels){diagnostic=pixels;});}
    catch(const std::runtime_error& error) {
        require(std::string(error.what())=="GPU probe changed a captured ghost tile","Tile-preservation fatal must remain unchanged");
        require(diagnostic==after && reads==2 && receipt.empty(),"Raw bytes must survive even an earlier tile-preservation failure without normal export credit");
        state.unchanged();target.dispose();return;
    }
    throw std::runtime_error("Mutated captured tile was accepted");
}
void diagnostic_sink_failure_propagates_without_export_credit() {
    ProbeFixture fixture;auto& target=fixture.target;auto& trails=fixture.trails;Snapshot state;std::string receipt;
    try {receipt=target.prepare_probe(trails,[](const auto&){throw std::runtime_error("diagnostic disk failure");});}
    catch(const std::runtime_error& error) {
        require(std::string(error.what())=="diagnostic disk failure","Diagnostic IO failure must preserve its context, not be replaced with a swatch failure");
        require(receipt.empty() && reads==2,"Diagnostic IO failure must stop normal export without extra read passes");
        state.unchanged();target.dispose();return;
    }
    throw std::runtime_error("Diagnostic IO failure was swallowed");
}
void unchanged_swatch_thresholds_parameterized() {
    for(const auto& point:trail_probe_swatches) for(unsigned channel=0;channel<4;++channel) for(int delta:{-2,-1,0,1,2}) {
        const int value=int(point.expected)+delta;if(value<0 || value>255) continue;
        ProbeFixture fixture;auto& target=fixture.target;auto& trails=fixture.trails;Snapshot state;
        std::vector<std::uint8_t> pixels(1048576);
        for(const auto& swatch:trail_probe_swatches) for(unsigned c=0;c<4;++c) pixels[((511-swatch.top)*512+swatch.x)*4+c]=std::uint8_t(swatch.expected);
        pixels[((511-point.top)*512+point.x)*4+channel]=std::uint8_t(value);readbacks={std::vector<std::uint8_t>(1048576),pixels};
        unsigned diagnostics=0;bool rejected=false;
        try {target.prepare_probe(trails,[&](const auto&){++diagnostics;});}
        catch(const std::runtime_error& error) {rejected=true;require(std::string(error.what()).find("GPU trail alpha/orientation swatch failed at ")==0,"Unexpected threshold rejection");}
        require(rejected==(std::abs(delta)>1) && diagnostics==1 && reads==2,"Every RGBA channel must retain the exact +/-1 threshold after diagnostic persistence");
        state.unchanged();target.dispose();
    }
}
void script_sweep(bool original_matches) {
    std::vector<std::uint8_t> pixels(1048576);
    for(const auto& point:trail_probe_swatches) for(unsigned c=0;c<4;++c) pixels[((511-point.top)*512+point.x)*4+c]=std::uint8_t(point.expected);
    if(!original_matches) for(unsigned c=0;c<4;++c) pixels[((511-454)*512+454)*4+c]=0;
    readbacks=std::vector<std::vector<std::uint8_t>>(7,pixels);readbacks.back().assign(786432,0);
    for(const auto& marker:trail_probe_markers) for(unsigned c=0;c<4;++c) {
        const unsigned pixel=(511-marker.top-2)*512+marker.x+2;
        readbacks[5][pixel*4+c]=marker.rgba[c];
        if(c<3) readbacks[6][pixel*3+c]=marker.rgba[c];
    }
}
std::string sweep_failure(ProbeFixture& fixture,const TrailProbeReadback& observe,const std::function<void(const std::string&)>& report) {
    try {fixture.target.diagnostic_sweep(fixture.trails,observe,report);}
    catch(const std::runtime_error& error) {return error.what();}
    throw std::runtime_error("Instrumented diagnostic matched swatches but returned normal acceptance");
}
void instrumented_matching_swatches_cannot_return_acceptance() {
    ProbeFixture fixture;script_sweep(true);Snapshot state;std::string records;
    const auto failure=sweep_failure(fixture,[](auto,const auto&){},[&](const auto& line){records+=line+'\n';});
    require(failure=="instrumented diagnostic completed; uninstrumented GPU acceptance disabled","Matching instrumented swatches and markers must fail explicitly");
    require(records.find("original_result=matched")!=std::string::npos,"Original matching result must be recorded without acceptance");
    require(reads==7 && read_formats.back()==GL_RGB && read_formats[5]==GL_RGBA,"Only full-size marker RGBA then RGB reads are allowed, without post-RGB read");
    require(marker_scissors==std::vector<bool>({true,false}),"Opaque marker quads must contrast scissor only, with blending disabled");
    state.unchanged();fixture.target.dispose();
}
void original_raw_and_failure_precede_markers_and_final_rethrow() {
    ProbeFixture fixture;script_sweep(false);Snapshot state;std::vector<TrailProbeRead> observed;std::string records;
    const auto original=readbacks[2];
    const auto failure=sweep_failure(fixture,[&](auto phase,const auto& pixels){
        observed.push_back(phase);
        if(phase==TrailProbeRead::original_post_mask) require(pixels==original && !markers_started,"Untouched original post-mask raw must precede marker mutation");
    },[&](const auto& line){
        if(line.find("original_result=")==0) require(!markers_started,"Original failure must be recorded before markers");
        records+=line+'\n';
    });
    require(observed==std::vector<TrailProbeRead>({TrailProbeRead::pre_mask,TrailProbeRead::original_post_mask,TrailProbeRead::paired_a,TrailProbeRead::paired_b,TrailProbeRead::marker_rgba,TrailProbeRead::marker_rgb}),"Diagnostic observation ordering changed");
    require(failure.find("GPU trail alpha/orientation swatch failed at 454,454; instrumented diagnostic;")==0,("Original fatal must lead the final composed failure: "+failure).c_str());
    require(records.find("original_result=failed cause=GPU trail alpha/orientation swatch failed at 454,454")!=std::string::npos,"Original failure must remain explicit");
    state.unchanged();fixture.target.dispose();
}
void retained_sentinel_pair_is_not_zero_readback() {
    ProbeFixture fixture;script_sweep(false);retained_reads={3,4};std::string records;
    sweep_failure(fixture,[&](auto phase,const auto& pixels){
        if(phase==TrailProbeRead::paired_a || phase==TrailProbeRead::paired_b) {
            const auto counts=trail_probe_read_counts(pixels,trail_probe_sentinel(phase));
            require(counts.changed==0 && counts.retained==1048576 && counts.zero==0,"An untouched sentinel buffer is no-write evidence, not observed zeros");
        }
    },[&](const auto& line){records+=line+'\n';});
    require(records.find("sentinel_pair classification=no_write bytes=1048576 retained_pairs=1048576")!=std::string::npos,"Contrasting retained sentinels must be classified explicitly");
    fixture.target.dispose();
}
void evidence_io_errors_do_not_hide_original_failure_or_other_artifacts() {
    ProbeFixture fixture;script_sweep(false);Snapshot state;std::vector<TrailProbeRead> attempts;
    const auto failure=sweep_failure(fixture,[&](auto phase,const auto&){
        attempts.push_back(phase);
        if(phase==TrailProbeRead::original_post_mask || phase==TrailProbeRead::marker_rgba || phase==TrailProbeRead::marker_rgb)
            throw std::runtime_error(std::string("exclusive write failed ")+trail_probe_read_name(phase));
    },[](const auto&){});
    require(attempts.size()==6,"Every available evidence phase must still be attempted after diagnostic IO failure");
    for(const auto* text:{"GPU trail alpha/orientation swatch failed at 454,454","exclusive write failed original_post_mask","exclusive write failed marker_rgba","exclusive write failed marker_rgb"})
        require(failure.find(text)!=std::string::npos,"Original validation and every IO failure context must survive final rethrow");
    state.unchanged();fixture.target.dispose();
}
void unsupported_rgb_is_reported_without_invented_bytes() {
    ProbeFixture fixture;script_sweep(false);rgb_error=true;Snapshot state;std::vector<TrailProbeRead> observed;
    const auto failure=sweep_failure(fixture,[&](auto phase,const auto&){observed.push_back(phase);},[](const auto&){});
    require(observed.size()==5 && observed.back()==TrailProbeRead::marker_rgba,"A failed RGB API must not produce invented RGB bytes");
    require(failure.find("marker_rgb: marker_rgb: GL error")!=std::string::npos,"Unsupported RGB context must be fatal and explicit");
    state.unchanged();fixture.target.dispose();
}
void unsupported_pack_query_is_reported_without_setting_pack_state() {
    ProbeFixture fixture;pack_error=true;Snapshot state;
    const auto failure=sweep_failure(fixture,[](auto,const auto&){},[](const auto&){});
    require(failure.find("clear color/pack state query: GL error")!=std::string::npos,"Unsupported pack queries must be reported, never replaced with assumed values");
    state.unchanged();fixture.target.dispose();
}
void restoration_error_preserves_original_failure_and_evidence() {
    ProbeFixture fixture;script_sweep(false);restore_error=true;Snapshot state;unsigned observed=0;
    const auto failure=sweep_failure(fixture,[&](auto,const auto&){++observed;},[](const auto&){});
    require(observed==6 && failure.find("GPU trail alpha/orientation swatch failed at 454,454")==0 &&
        failure.find("marker_sweep: instrumented marker state restoration: GL error")!=std::string::npos,"Restoration failure must retain original fatal and all available readbacks");
    state.unchanged();fixture.target.dispose();
}
void observable_gameplay_tile_change_is_reported_after_marker_exports() {
    ProbeFixture fixture;script_sweep(false);readbacks[5][448*512*4]=7;std::string records;unsigned observed=0;
    const auto failure=sweep_failure(fixture,[&](auto,const auto&){++observed;},[&](const auto& line){records+=line+'\n';});
    require(observed==6 && records.find("checked_bytes=16384 changed_bytes=1 unobservable_bytes=0")!=std::string::npos &&
        failure.find("markers changed observable captured ghost bytes")!=std::string::npos,"Observable gameplay tile changes must be recorded without losing marker exports");
    fixture.target.dispose();
}
void unrecordable_original_result_does_not_mutate_markers() {
    ProbeFixture fixture;script_sweep(false);Snapshot state;
    const auto failure=sweep_failure(fixture,[](auto,const auto&){},[](const auto& line){if(line.find("original_result=")==0)throw std::runtime_error("original result log failed");});
    require(!markers_started && reads==3 && failure.find("original result log failed")!=std::string::npos,"Marker mutation must not proceed if the original result cannot be recorded");
    state.unchanged();fixture.target.dispose();
}
void bounded_matrix_model_rejects_push_without_increment_parameterized() {
    for(auto mode:{GL_PROJECTION,GL_MODELVIEW}) {
        reset();glMatrixMode(mode);const auto original=matrices.at(mode).current;
        const unsigned limit=mode==GL_PROJECTION ? 2 : 32;
        for(unsigned i=1;i<limit;++i) glPushMatrix();
        require(matrices.at(mode).depth==limit,"Pinned matrix stack must start at counter1 and reach its real limit");
        glPushMatrix();require(glGetError()==GL_STACK_OVERFLOW && matrices.at(mode).depth==limit,"Failed push must report1283 without consuming a stack entry");
        for(unsigned i=1;i<limit;++i) glPopMatrix();
        require(glGetError()==GL_NO_ERROR && matrices.at(mode).depth==1 && matrices.at(mode).current==original,"Caller matrix stack must restore after balanced successful pushes only");
    }
}
void nested_sweep_uses_no_caller_stack_entries_parameterized() {
    for(unsigned depth:{1u,2u}) for(auto mode:{GL_PROJECTION,GL_MODELVIEW}) {
        ProbeFixture fixture;script_sweep(false);
        if(depth==2) {glMatrixMode(GL_PROJECTION);glPushMatrix();glMatrixMode(GL_MODELVIEW);glPushMatrix();}
        glMatrixMode(mode);Snapshot state;pushes=pops=overflows=0;
        std::vector<TrailProbeRead> phases;
        const auto failure=sweep_failure(fixture,[&](auto phase,const auto&) {
            phases.push_back(phase);
            require(matrices.at(GL_PROJECTION).depth==depth && matrices.at(GL_MODELVIEW).depth==depth,"Nested premask/marker reads must leave caller counters untouched");
        },[](const auto&){});
        require(overflows==0,("Nested premask/marker guard hit finite projection-stack overflow1283: "+failure).c_str());
        require(phases.size()==6 && reads==7,"Both actual nested premask and marker read paths must complete their evidence observations");
        require(pushes==0 && pops==0,"State preservation must consume no projection/modelview stack entries");
        require(failure.find("GPU trail alpha/orientation swatch failed at 454,454")==0,"Unconditional diagnostic failure must retain the original swatch cause after clean state restoration");
        state.unchanged();require(glGetError()==GL_NO_ERROR,"Successful guard restoration must not leave hidden GL errors");fixture.target.dispose();
    }
}
void constructor_query_failure_does_not_mutate_state() {
    ProbeFixture fixture;Snapshot state;pushes=pops=0;matrix_query_error=true;bool rejected=false;
    try {fixture.target.read_rgba();}
    catch(const std::runtime_error& error) {rejected=true;require(std::string(error.what()).find("trail state capture: GL error")==0,"Capture query error must fail at guard entry");}
    require(rejected && reads==0 && pushes==0 && pops==0,"Failed state capture must not mutate mode, consume stacks or start a read");
    state.unchanged();fixture.target.dispose();
}
void callback_failure_restores_real_matrices_at_caller_limit_parameterized() {
    for(auto mode:{GL_PROJECTION,GL_MODELVIEW}) {
        ProbeFixture fixture;fixture.trails.add(fixture.player,fixture.presentation.pose());
        glMatrixMode(GL_PROJECTION);glPushMatrix();glMatrixMode(GL_MODELVIEW);glPushMatrix();glMatrixMode(mode);
        Snapshot state;pushes=pops=0;bool rejected=false;
        try {fixture.target.capture(fixture.trails,fixture.presentation,fixture.player,[](unsigned,const auto&){throw std::runtime_error("capture callback failed");});}
        catch(const std::runtime_error& error) {rejected=true;require(std::string(error.what())=="capture callback failed","Restoration must retain an original callback error");}
        require(rejected && pushes==0 && pops==0,"Callback failure must restore without consuming caller stack entries");
        state.unchanged();fixture.target.dispose();
    }
}
void callback_and_restoration_errors_are_both_reported() {
    ProbeFixture fixture;fixture.trails.add(fixture.player,fixture.presentation.pose());Snapshot state;std::string failure;bool original_nested=false;
    try {fixture.target.capture(fixture.trails,fixture.presentation,fixture.player,[](unsigned,const auto&){matrix_restore_error=true;throw std::runtime_error("capture callback failed");});}
    catch(const std::runtime_error& error) {
        failure=error.what();
        try {std::rethrow_if_nested(error);}
        catch(const std::runtime_error& original) {original_nested=std::string(original.what())=="capture callback failed";}
    }
    require(failure.find("capture callback failed")==0 && failure.find("GL error")!=std::string::npos,
        ("Callback cleanup silently lost restoration GL error: "+failure).c_str());
    require(original_nested,"Combined restoration failure must retain the original exception as its nested cause");
    state.unchanged();require(glGetError()==GL_NO_ERROR,"Reported restoration error must not remain silently pending");fixture.target.dispose();
}
void callback_and_silent_matrix_restore_corruption_are_both_reported() {
    ProbeFixture fixture;fixture.trails.add(fixture.player,fixture.presentation.pose());const auto projection=matrices.at(GL_PROJECTION).current;std::string failure;
    try {fixture.target.capture(fixture.trails,fixture.presentation,fixture.player,[](unsigned,const auto&){matrix_restore_corrupt=true;throw std::runtime_error("capture callback failed");});}
    catch(const std::runtime_error& error) {failure=error.what();}
    require(failure.find("capture callback failed")==0 && failure.find("Trail pass failed native GL state restoration")!=std::string::npos,
        "Callback cleanup must report value mismatch instead of silently restoring a corrupt matrix");
    require(matrices.at(GL_PROJECTION).current!=projection,"Injected restore corruption must not be falsely reported as preserved state");fixture.target.dispose();
}
void nonstandard_callback_exception_restores_state_and_preserves_value() {
    ProbeFixture fixture;fixture.trails.add(fixture.player,fixture.presentation.pose());Snapshot state;bool rejected=false;
    try {fixture.target.capture(fixture.trails,fixture.presentation,fixture.player,[](unsigned,const auto&){throw 42;});}
    catch(int value) {rejected=true;require(value==42,"Guard must preserve a nonstandard original callback exception");}
    require(rejected,"Expected nonstandard callback exception");state.unchanged();fixture.target.dispose();
}
void callback_pending_gl_error_is_reported_without_losing_state() {
    ProbeFixture fixture;fixture.trails.add(fixture.player,fixture.presentation.pose());Snapshot state;std::string failure;
    try {fixture.target.capture(fixture.trails,fixture.presentation,fixture.player,[](unsigned,const auto&){pending_error=GL_INVALID_ENUM;throw std::runtime_error("capture IO failed");});}
    catch(const std::runtime_error& error) {failure=error.what();}
    require(failure.find("capture IO failed; GL error before state restoration")==0,"A callback's pending GL error must not be silently consumed during cleanup");
    state.unchanged();require(glGetError()==GL_NO_ERROR,"Reported pending GL error must be handled explicitly");fixture.target.dispose();
}
}

extern "C" {
unsigned glGetError(){const auto error=pending_error;pending_error=GL_NO_ERROR;return error;}
void glGetIntegerv(unsigned name,int* out){if(name==GL_PACK_ALIGNMENT && pack_error){pending_error=GL_INVALID_ENUM;return;}if(name==GL_VIEWPORT)std::copy(viewport.begin(),viewport.end(),out);else if(name==GL_SCISSOR_BOX)std::copy(scissor.begin(),scissor.end(),out);else *out=values.at(name);}
void glGetFloatv(unsigned name,float* out){
    if(name==GL_PROJECTION_MATRIX && matrix_query_error){matrix_query_error=false;pending_error=GL_INVALID_ENUM;return;}
    if(name==GL_PROJECTION_MATRIX || name==GL_MODELVIEW_MATRIX) {
        const auto& matrix=matrices.at(name==GL_PROJECTION_MATRIX ? GL_PROJECTION : GL_MODELVIEW).current;
        for(unsigned row=0;row<4;++row) for(unsigned col=0;col<4;++col) out[col*4+row]=matrix[row*4+col];
    } else {const auto& source=name==GL_COLOR_CLEAR_VALUE ? clear_color : color;std::copy(source.begin(),source.end(),out);}
}
bool glIsEnabled(unsigned cap){return enabled.count(cap);}
void glEnable(unsigned cap){enabled.insert(cap);}void glDisable(unsigned cap){enabled.erase(cap);}
void glMatrixMode(unsigned mode){values[GL_MATRIX_MODE]=int(mode);}
void glPushMatrix(){auto& matrix=matrices.at(unsigned(values.at(GL_MATRIX_MODE)));++pushes;if(matrix.depth>=matrix.stack.size()){pending_error=GL_STACK_OVERFLOW;++overflows;return;}matrix.stack[matrix.depth++]=matrix.current;}
void glPopMatrix(){auto& matrix=matrices.at(unsigned(values.at(GL_MATRIX_MODE)));++pops;if(matrix.depth==0){pending_error=GL_STACK_UNDERFLOW;return;}matrix.current=matrix.stack[--matrix.depth];}
void glBindFramebuffer(unsigned name,unsigned id){if(name!=GL_READ_FRAMEBUFFER)values[GL_FRAMEBUFFER_BINDING]=int(id);if(name!=GL_DRAW_FRAMEBUFFER)values[GL_READ_FRAMEBUFFER_BINDING]=int(id);}
void glBindTexture(unsigned,unsigned id){values[GL_TEXTURE_BINDING_2D]=int(id);}
void glViewport(int x,int y,int w,int h){viewport={x,y,w,h};}void glScissor(int x,int y,int w,int h){scissor={x,y,w,h};scissors.push_back(scissor);}
void glColor4f(float r,float g,float b,float a){color={r,g,b,a};}void glColor4ub(unsigned char r,unsigned char g,unsigned char b,unsigned char a){glColor4f(r/255.f,g/255.f,b/255.f,a/255.f);}
void glClearColor(float r,float g,float b,float a){clear_color={r,g,b,a};if(markers_started && restore_error && r==0.6f){pending_error=GL_INVALID_ENUM;restore_error=false;}}
void glClear(unsigned mask){require(mask==GL_COLOR_BUFFER_BIT && enabled.count(GL_SCISSOR_TEST) && scissor==std::array<int,4>{448,0,64,64},"Clear marker must be restricted to unused tile63");markers_started=true;}
void glBlendFuncSeparate(unsigned s,unsigned d,unsigned a,unsigned b){values[GL_BLEND_SRC_RGB]=int(s);values[GL_BLEND_DST_RGB]=int(d);values[GL_BLEND_SRC_ALPHA]=int(a);values[GL_BLEND_DST_ALPHA]=int(b);}
void glBlendFunc(unsigned s,unsigned d){blends.push_back({s,d});glBlendFuncSeparate(s,d,s,d);}
void glBlendEquationSeparate(unsigned a,unsigned b){values[GL_BLEND_EQUATION_RGB]=int(a);values[GL_BLEND_EQUATION_ALPHA]=int(b);}void glBlendEquation(unsigned v){glBlendEquationSeparate(v,v);}
void glGenTextures(int,unsigned* out){*out=77;}void glGenFramebuffers(int,unsigned* out){*out=88;++allocations;}
void glTexParameteri(unsigned,unsigned,int){}void glTexImage2D(unsigned,int,int,int w,int h,int,unsigned,unsigned,const void*){require(w==512 && h==512,"Trail target dimensions changed");}
void glFramebufferTexture2D(unsigned,unsigned,unsigned,unsigned,int){}unsigned glCheckFramebufferStatus(unsigned){return incomplete ? 0 : GL_FRAMEBUFFER_COMPLETE;}
void glDeleteFramebuffers(int,const unsigned*){++deletions;}void glDeleteTextures(int,const unsigned*){}
void glLoadMatrixf(const float* input){
    if(matrix_restore_corrupt){matrix_restore_corrupt=false;return;}
    auto& matrix=matrices.at(unsigned(values.at(GL_MATRIX_MODE))).current;
    for(unsigned row=0;row<4;++row)for(unsigned col=0;col<4;++col)matrix[row*4+col]=input[col*4+row];
    if(matrix_restore_error){matrix_restore_error=false;pending_error=GL_INVALID_ENUM;}
}
void glLoadIdentity(){const Matrix identity{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1};matrices.at(unsigned(values.at(GL_MATRIX_MODE))).current=identity;}
void glOrtho(double left,double right,double bottom,double top,double near,double far){
    const Matrix ortho{float(2/(right-left)),0,0,float(-(right+left)/(right-left)),0,float(2/(top-bottom)),0,float(-(top+bottom)/(top-bottom)),
        0,0,float(-2/(far-near)),float(-(far+near)/(far-near)),0,0,0,1};
    auto& matrix=matrices.at(unsigned(values.at(GL_MATRIX_MODE))).current;Matrix product{};
    for(unsigned row=0;row<4;++row)for(unsigned col=0;col<4;++col)for(unsigned k=0;k<4;++k)product[row*4+col]+=matrix[row*4+k]*ortho[k*4+col];
    matrix=product;
}
void glBegin(unsigned){++draws;if(markers_started){require(!enabled.count(GL_BLEND),"Opaque marker quads must disable blending");marker_scissors.push_back(enabled.count(GL_SCISSOR_TEST));}}void glEnd(){}void glVertex2f(float x,float y){if(markers_started)require(x>=448 && x<=512 && y>=448 && y<=512,"Unscissored marker geometry must remain inside unused tile63");}void glTexCoord2f(float u,float v){uv.push_back({u,v});}
void glFinish(){}void glReadPixels(int x,int y,int width,int height,unsigned format,unsigned type,void* out){
    require(values[GL_READ_FRAMEBUFFER_BINDING]==88,"Readback must bind actual trail attachment");
    require(x==0 && y==0 && width==512 && height==512 && type==GL_UNSIGNED_BYTE,"Diagnostic reads must use the complete unchanged attachment");
    read_formats.push_back(format);
    if(format==GL_RGB && rgb_error){pending_error=GL_INVALID_ENUM;++reads;return;}
    if(!readbacks.empty()) {
        require(reads<readbacks.size(),"Unexpected additional readback");require(readbacks[reads].size()==unsigned(512*512*(format==GL_RGB ? 3 : 4)),"Readback format byte count changed");
        if(readbacks.size()==7 && reads!=0 && reads!=2) {
            const auto phase=reads==1 ? TrailProbeRead::pre_mask : reads==3 ? TrailProbeRead::paired_a : reads==4 ? TrailProbeRead::paired_b : reads==5 ? TrailProbeRead::marker_rgba : TrailProbeRead::marker_rgb;
            const auto* bytes=static_cast<std::uint8_t*>(out);require(std::all_of(bytes,bytes+readbacks[reads].size(),[&](auto byte){return byte==trail_probe_sentinel(phase);}),"New read buffers must have explicit contrasting nonzero sentinels before the API call");
        }
        if(!retained_reads.count(reads)) std::copy(readbacks[reads].begin(),readbacks[reads].end(),static_cast<std::uint8_t*>(out));
    }
    ++reads;
}
}
int main() {
    try {
        for(auto test:{bounded_matrix_model_rejects_push_without_increment_parameterized,nested_sweep_uses_no_caller_stack_entries_parameterized,
            constructor_query_failure_does_not_mutate_state,callback_failure_restores_real_matrices_at_caller_limit_parameterized,
            callback_and_restoration_errors_are_both_reported,callback_and_silent_matrix_restore_corruption_are_both_reported,
            nonstandard_callback_exception_restores_state_and_preserves_value,
            callback_pending_gl_error_is_reported_without_losing_state,
            capture_masks_completed_tile_and_restores_state,tile_reuse_clears_only_reused_tile,
            target_uv_and_fade_are_applied_once_per_snapshot,incomplete_target_fails_without_committing_bitmap,
            attachment_readback_restores_independent_read_write_targets,diagnostic_precedes_swatch_failure_with_untouched_bytes,
            diagnostic_precedes_tile_preservation_failure,diagnostic_sink_failure_propagates_without_export_credit,
            unchanged_swatch_thresholds_parameterized,instrumented_matching_swatches_cannot_return_acceptance,
            original_raw_and_failure_precede_markers_and_final_rethrow,retained_sentinel_pair_is_not_zero_readback,
            evidence_io_errors_do_not_hide_original_failure_or_other_artifacts,unsupported_rgb_is_reported_without_invented_bytes,
            unsupported_pack_query_is_reported_without_setting_pack_state,restoration_error_preserves_original_failure_and_evidence,
            observable_gameplay_tile_change_is_reported_after_marker_exports,unrecordable_original_result_does_not_mutate_markers}) test();
        std::cout<<"Diagnostic ordering/IO seams passed; scripted host readbacks are not GPU mathematics or fidelity proof\n";
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
