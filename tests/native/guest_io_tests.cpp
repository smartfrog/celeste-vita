#include "guest_io.hpp"
#include "guest_dash_probe_diagnostic.hpp"
#include "normal_outputs.hpp"
#include "capture_policy.hpp"
#include "lifecycle_fixture.hpp"
#include "guest_file_fixture.hpp"
#include <algorithm>
#include <array>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

using namespace celeste::diagnostic;

namespace {
using namespace guest_test;

void expect(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
template<class F> void rejects(F action, const std::string& text) {
    try { action(); }
    catch (const std::exception& error) {
        expect(std::string(error.what()).find(text) != std::string::npos, "Unexpected error text");
        return;
    }
    throw std::runtime_error("Expected rejection");
}

void missing_pair_is_absent() {
    reset();
    expect(!guest_capture_exists("/data/frame.ppm"), "Missing pair must be absent");
    expect(opens == 0, "Availability check must not open outputs");
}

void complete_pair_preserves_without_opening() {
    reset();
    stored["/data/frame.ppm"] = {"old-image"};
    stored["/data/frame.ppm.txt"] = {"old-receipt"};
    expect(guest_capture_exists("/data/frame.ppm"), "Complete pair must be detected");
    expect(opens == 0 && !stored.empty(), "Complete pair must not be opened or replaced");
    expect(stored["/data/frame.ppm"].data == "old-image" && stored["/data/frame.ppm.txt"].data == "old-receipt",
           "Complete pair content must be preserved");
}

void partial_pair_is_present_parameterized() {
    reset();
    stored["/data/frame.ppm"] = {"old-image"};
    expect(guest_capture_exists("/data/frame.ppm"), "Image-only pair must be treated as existing");
    reset();
    stored["/data/frame.ppm.txt"] = {"old-receipt"};
    expect(guest_capture_exists("/data/frame.ppm"), "Receipt-only pair must be treated as existing");
    expect(opens == 0, "Partial pair must not be opened");
}

void fresh_pair_writes_both_closed_outputs() {
    reset();
    const std::string image = "P6\n1 1\n255\nrgb";
    const std::string receipt = "frame_saved path=/data/frame.ppm\n";
    expect(!guest_capture_exists("/data/frame.ppm"), "Fresh pair must be absent");
    write_guest_file("/data/frame.ppm",image,SCE_O_EXCL);
    write_guest_file("/data/frame.ppm.txt",receipt,SCE_O_EXCL);
    expect(opens == 2 && closes == 2, "Fresh image/receipt must each open and close");
    expect((last_open_flags & (SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL)) == (SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL),
           "Fresh output must stay exclusive");
    expect(stored.at("/data/frame.ppm").data == image && stored.at("/data/frame.ppm.txt").data == receipt,
           "Fresh pair content must be complete");
    expect(guest_capture_exists("/data/frame.ppm"), "Fresh pair must become an existing pair");
}

void existing_output_excl_writer_fails_and_preserves() {
    reset();
    stored["/data/frame.ppm"] = {"old-image"};
    rejects([&] { write_guest_file("/data/frame.ppm","new-image",SCE_O_EXCL); },"open failed");
    expect(stored.at("/data/frame.ppm").data == "old-image", "Existing image must not be overwritten");
    expect(closes == 0, "Failed exclusive open must not close a handle");
}

void unexpected_stat_error_is_not_treated_as_missing() {
    reset();
    stat_error = error(13);
    rejects([&] { guest_capture_exists("/data/frame.ppm"); },"stat failed");
    expect(opens == 0, "Unexpected stat error must not fall through to writing");
}

void kernel_error_with_errno_low_bits_is_not_missing() {
    reset();
    stat_error = static_cast<int>(0x80020002u);
    rejects([&] { guest_capture_exists("/data/frame.ppm"); },"stat failed");
    expect(opens == 0, "Non-errno SDK error with low bits 2 must not be treated as ENOENT");
}

void oversized_output_rejected_before_open() {
    reset();
    const std::string too_large(2*1024*1024+1,'x');
    rejects([&] { write_guest_file("/data/frame.ppm",too_large,SCE_O_EXCL); },"exceeds bounded");
    expect(opens == 0, "Oversized output must be rejected before the filesystem");
}

void partial_write_is_reported_after_close() {
    reset();
    write_error = 1;
    rejects([&] { write_guest_file("/data/frame.ppm","data",SCE_O_EXCL); },"write/close failed");
    expect(closes == 1, "Partial write must still close its handle");
    expect(open_files.empty(), "Failed write must not leak the simulated handle");
}

void close_failure_is_reported() {
    reset();
    close_error = error(5);
    rejects([&] { write_guest_file("/data/frame.ppm","data",SCE_O_EXCL); },"write/close failed");
    expect(closes == 1, "Close failure must be reported");
}
std::unique_ptr<FILE,int(*)(FILE*)> diagnostic_log() {
    const auto path=std::string(CELESTE_GUEST_IO_TEST_DIRECTORY)+"/dash-probe-diagnostic-test.log";
    std::unique_ptr<FILE,int(*)(FILE*)> log(std::fopen(path.c_str(),"w+x"),&std::fclose);
    expect(bool(log),"Diagnostic test log must open");
    expect(std::remove(path.c_str())==0,"Owned diagnostic test log must become anonymous");
    return log;
}
void diagnostic_bytes_and_all_expected_and_mirrored_channels_are_reported() {
    reset();auto log=diagnostic_log();std::vector<std::uint8_t> pixels(1048576);
    for(unsigned i=0;i<pixels.size();++i) pixels[i]=std::uint8_t(i*37u+11u);
    const std::array<std::array<unsigned,7>,4> points{{
        {454,454,57,118552,454,931608,128},{462,454,57,118584,454,931640,192},
        {486,454,57,118680,454,931736,255},{486,470,41,85912,470,964504,64}}};
    for(unsigned i=0;i<points.size();++i) for(unsigned channel=0;channel<4;++channel) {
        pixels[points[i][3]+channel]=std::uint8_t(11+i*17+channel);
        pixels[points[i][5]+channel]=std::uint8_t(201-i*11-channel);
    }
    write_dash_probe_diagnostic(pixels,"test-revision",57,log.get());
    const std::string path="ux0:data/celeste_native_room-test-revision-dash-probe-diagnostic.trail.rgba";
    expect(stored.at(path).data==std::string(reinterpret_cast<const char*>(pixels.data()),pixels.size()),"Diagnostic writer must preserve every raw byte");
    expect(opens==1 && closes==1 && (last_open_flags&SCE_O_EXCL),"Diagnostic output must be exclusively written and closed");
    std::rewind(log.get());char line[768];
    for(unsigned i=0;i<points.size();++i) {
        expect(std::fgets(line,sizeof(line),log.get())!=nullptr,"All four swatches must be logged before validation");
        const std::string text=line;const auto& p=points[i];
        for(const auto& field:{"x="+std::to_string(p[0]),"top="+std::to_string(p[1]),"row="+std::to_string(p[2]),"offset="+std::to_string(p[3]),
                              "mirrored_row="+std::to_string(p[4]),"mirrored_offset="+std::to_string(p[5])})
            expect(text.find(" "+field+" ")!=std::string::npos,"Diagnostic coordinate or byte offset differs from the unchanged buffer layout");
        std::string actual,mirror,expected;
        for(unsigned c=0;c<4;++c) {
            const auto separator=c ? "," : "";
            actual+=separator+std::to_string(11+i*17+c);mirror+=separator+std::to_string(201-i*11-c);expected+=separator+std::to_string(p[6]);
        }
        expect(text.find(" actual_rgba="+actual+" ")!=std::string::npos && text.find(" mirrored_rgba="+mirror+" ")!=std::string::npos &&
               text.find(" expected_rgba="+expected+" ")!=std::string::npos,"Diagnostic must report all four original channels at both row interpretations");
        expect(text.find("revision=test-revision frame=57 width=512 height=512 bytes=1048576 layout=GL_bottom_up_RGBA8")!=std::string::npos,
               "Diagnostic records must bind source, frame, dimensions and uninterpreted raw layout");
        expect(text.find("diagnostic_only=1 accepted_frame=0 fresh_export=0 native_probe_checks=0 full_completion=0")!=std::string::npos,
               "Diagnostic output must never claim normal-frame or completion credit");
    }
    expect(std::fgetc(log.get())==EOF && !std::ferror(log.get()),"Diagnostic log must contain exactly four complete records");
}
void diagnostic_write_failures_are_fatal_parameterized() {
    for(unsigned failure:{0u,1u,2u}) {
        reset();auto log=diagnostic_log();
        const std::string path="ux0:data/celeste_native_room-test-revision-dash-probe-diagnostic.trail.rgba";
        if(failure==0) stored[path]={"prior diagnostic"};
        if(failure==1) write_error=1;
        if(failure==2) close_error=error(5);
        rejects([&]{write_dash_probe_diagnostic(std::vector<std::uint8_t>(1048576),"test-revision",57,log.get());},
                failure==0 ? "open failed: "+path : "write/close failed: "+path);
        if(failure==0) expect(stored.at(path).data=="prior diagnostic","Old diagnostic evidence must survive exclusive-open failure");
        expect(open_files.empty(),"Failed diagnostic writes must not leak handles");
        std::rewind(log.get());expect(std::fgetc(log.get())==EOF,"Unclosed diagnostic output must not be logged as saved");
    }
}
void invalid_diagnostic_size_is_rejected_before_open() {
    reset();auto log=diagnostic_log();
    rejects([&]{write_dash_probe_diagnostic(std::vector<std::uint8_t>(1048575),"test-revision",57,log.get());},"exact RGBA bytes");
    expect(opens==0,"Malformed diagnostic bytes must not reach guest IO");
}
void sentinel_pair_classification_parameterized() {
    struct Case {std::vector<std::uint8_t> first,second;const char* expected;};
    for(const auto& item:std::vector<Case>{{{0xa5,0xa5},{0x5a,0x5a},"no_write"},{{0,0},{0,0},"consistent_overwrite"},
             {{0,0xa5},{0,0x5a},"partial_no_write"},{{1,2},{1,3},"differing_reads"},{{0xa5,1},{0xa5,1},"consistent_overwrite"}}) {
        const auto pair=trail_probe_pair_counts(item.first,item.second);
        expect(std::string(pair.classification)==item.expected,"Contrasting sentinels must distinguish no-write from overwritten zeros and mixed reads");
        const auto counts=trail_probe_read_counts(item.first,0xa5);unsigned histogram_bytes=0;
        for(auto count:counts.histogram) histogram_bytes+=count;
        expect(counts.changed+counts.retained==item.first.size() && histogram_bytes==item.first.size(),"Changed/retained counts and histogram must cover every untouched raw byte");
    }
}
void sweep_exports_exactly_three_distinct_untouched_raw_artifacts() {
    reset();auto log=diagnostic_log();const std::string revision(109,'a');
    const auto prefix="ux0:data/celeste_native_room-"+revision;
    const std::array<TrailProbeRead,3> phases{TrailProbeRead::original_post_mask,TrailProbeRead::marker_rgba,TrailProbeRead::marker_rgb};
    const std::array<std::string,3> suffixes{"-dash-probe-diagnostic.trail.rgba","-dash-probe-diagnostic-markers.trail.rgba","-dash-probe-diagnostic-markers.trail.rgb"};
    unsigned total=0;
    for(unsigned index=0;index<phases.size();++index) {
        std::vector<std::uint8_t> pixels(512*512*trail_probe_channels(phases[index]));
        for(unsigned i=0;i<pixels.size();++i) pixels[i]=std::uint8_t(i*(17+index*2)+index+5);
        write_dash_probe_sweep_read(phases[index],pixels,revision.c_str(),57,log.get());
        expect(stored.at(prefix+suffixes[index]).data==std::string(reinterpret_cast<const char*>(pixels.data()),pixels.size()),"Each diagnostic raw artifact must retain all original bytes, format and identity");
        total+=pixels.size();
    }
    for(auto phase:{TrailProbeRead::pre_mask,TrailProbeRead::paired_a,TrailProbeRead::paired_b})
        write_dash_probe_sweep_read(phase,std::vector<std::uint8_t>(1048576,trail_probe_sentinel(phase)),revision.c_str(),57,log.get());
    expect(stored.size()==3 && opens==3 && closes==3 && total==2883584,"Only the exact three authorized raw arrays may be exported");
    std::rewind(log.get());char line[768];unsigned rgb_samples=0;
    while(std::fgets(line,sizeof(line),log.get())) {
        const std::string text=line;
        expect(text.back()=='\n' && text.find("instrumented=1 uninstrumented_proof=0")!=std::string::npos,"Every bounded record must mark the run as instrumented, never uninstrumented proof");
        if(text.find("sample phase=marker_rgb ")!=std::string::npos) {
            ++rgb_samples;const auto start=text.find(" actual=")+8,end=text.find(' ',start);
            const auto actual=text.substr(start,end-start);
            if(std::count(actual.begin(),actual.end(),',')!=2 || text.find("channels=3")==std::string::npos)
                throw std::runtime_error("RGB records must report exactly three observed channels, never invented alpha: actual="+actual+" record="+text);
        }
    }
    expect(!std::ferror(log.get()) && rgb_samples==3,"All three marker RGB samples must be reported after raw persistence");
}
void all_sweep_raw_io_failures_preserve_prior_files_parameterized() {
    for(auto phase:{TrailProbeRead::original_post_mask,TrailProbeRead::marker_rgba,TrailProbeRead::marker_rgb}) for(unsigned failure:{0u,1u,2u}) {
        reset();auto log=diagnostic_log();
        const auto path=std::string("ux0:data/celeste_native_room-r")+(phase==TrailProbeRead::original_post_mask ? "-dash-probe-diagnostic.trail.rgba" :
            phase==TrailProbeRead::marker_rgba ? "-dash-probe-diagnostic-markers.trail.rgba" : "-dash-probe-diagnostic-markers.trail.rgb");
        if(failure==0) stored[path]={"previous raw"};
        if(failure==1) write_error=1;
        if(failure==2) close_error=error(5);
        rejects([&]{write_dash_probe_sweep_read(phase,std::vector<std::uint8_t>(512*512*trail_probe_channels(phase)),"r",57,log.get());},
            failure==0 ? "open failed: "+path : "write/close failed: "+path);
        if(failure==0) expect(stored.at(path).data=="previous raw","Exclusive diagnostic IO must preserve each previous raw artifact");
        expect(open_files.empty(),"Every diagnostic write failure must release its handle");
    }
}
void sweep_formats_are_strict_parameterized() {
    for(auto phase:{TrailProbeRead::original_post_mask,TrailProbeRead::marker_rgba,TrailProbeRead::marker_rgb}) {
        reset();auto log=diagnostic_log();
        const auto wrong_size=phase==TrailProbeRead::marker_rgb ? 1048576 : 786432;
        rejects([&]{write_dash_probe_sweep_read(phase,std::vector<std::uint8_t>(wrong_size),"r",57,log.get());},"exact RGB/RGBA bytes");
        expect(opens==0,"Wrong RGB/RGBA byte formats must fail before opening outputs");
    }
}
#include "normal_outputs_cases.hpp"
}

int main() {
    int failed = 0;
    for (auto test : {missing_pair_is_absent, complete_pair_preserves_without_opening,
         partial_pair_is_present_parameterized, fresh_pair_writes_both_closed_outputs,
         existing_output_excl_writer_fails_and_preserves, unexpected_stat_error_is_not_treated_as_missing,
         kernel_error_with_errno_low_bits_is_not_missing, oversized_output_rejected_before_open,
          partial_write_is_reported_after_close, close_failure_is_reported,
          diagnostic_bytes_and_all_expected_and_mirrored_channels_are_reported,diagnostic_write_failures_are_fatal_parameterized,
          invalid_diagnostic_size_is_rejected_before_open,sentinel_pair_classification_parameterized,
          sweep_exports_exactly_three_distinct_untouched_raw_artifacts,all_sweep_raw_io_failures_preserve_prior_files_parameterized,sweep_formats_are_strict_parameterized,
          legacy_collision_composes_to_strict_capture_failure,two_launches_preserve_all_prior_outputs,
          normal_orphan_collisions_parameterized,normal_namespace_exhaustion,normal_stat_failure_parameterized,
          normal_claim_failures_parameterized,normal_wrong_binding_parameterized,normal_invalid_inputs_parameterized,
          full_revision_does_not_expand_normal_filenames,normal_receipt_binding_corruption_parameterized}) {
        try { test(); }
        catch (const std::exception& error) { std::cerr << error.what() << '\n'; ++failed; }
    }
    std::cout << "guest io cases=27 failed=" << failed << "; synthetic diagnostic bytes are not GPU proof\n";
    return failed ? 1 : 0;
}
