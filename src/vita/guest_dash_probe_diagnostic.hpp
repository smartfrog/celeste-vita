#pragma once
#include "guest_io.hpp"
#include "guest_record.hpp"
#include "trail_target.hpp"

namespace celeste::diagnostic {

inline void write_dash_probe_diagnostic(const std::vector<std::uint8_t>& pixels,const char* revision,unsigned frame,FILE* log) {
    if(pixels.size()!=512*512*4 || !revision || !*revision || !log)
        throw std::invalid_argument("Dash probe diagnostic requires exact RGBA bytes, source revision and log");
    const auto path=std::string("ux0:data/celeste_native_room-")+revision+"-dash-probe-diagnostic.trail.rgba";
    write_guest_file(path.c_str(),std::string_view(reinterpret_cast<const char*>(pixels.data()),pixels.size()),SCE_O_EXCL);
    for(const auto& point:trail_probe_swatches) {
        const unsigned row=511-point.top,offset=(row*512+point.x)*4,mirrored_offset=(point.top*512+point.x)*4;
        const auto record=bounded_guest_record<768>("Dash probe diagnostic record exceeds bound",
            "guest_dash_probe_diagnostic path=%s revision=%s frame=%u width=512 height=512 bytes=1048576 layout=GL_bottom_up_RGBA8 swatch=%s x=%u top=%u row=%u offset=%u expected_rgba=%u,%u,%u,%u actual_rgba=%u,%u,%u,%u mirrored_row=%u mirrored_offset=%u mirrored_rgba=%u,%u,%u,%u diagnostic_only=1 accepted_frame=0 fresh_export=0 native_probe_checks=0 full_completion=0 instrumented=1 uninstrumented_proof=0",
            path.c_str(),revision,frame,point.name,point.x,point.top,row,offset,point.expected,point.expected,point.expected,point.expected,
            unsigned(pixels[offset]),unsigned(pixels[offset+1]),unsigned(pixels[offset+2]),unsigned(pixels[offset+3]),point.top,mirrored_offset,
            unsigned(pixels[mirrored_offset]),unsigned(pixels[mirrored_offset+1]),unsigned(pixels[mirrored_offset+2]),unsigned(pixels[mirrored_offset+3]));
        if(std::fprintf(log,"%s\n",record.c_str())<0 || std::fflush(log))
            throw std::runtime_error("Dash probe diagnostic log write/flush failed: "+path);
    }
}

inline void write_dash_probe_sweep_event(const std::string& event,const char* revision,unsigned frame,FILE* log) {
    if(!revision || !*revision || !log) throw std::invalid_argument("Instrumented sweep event requires revision and log");
    const auto record=bounded_guest_record<768>("Instrumented sweep event exceeds bound",
        "guest_dash_probe_sweep revision=%s frame=%u instrumented=1 uninstrumented_proof=0 diagnostic_only=1 accepted_frame=0 fresh_export=0 native_probe_checks=0 full_completion=0 %s",
        revision,frame,event.c_str());
    if(std::fprintf(log,"%s\n",record.c_str())<0 || std::fflush(log)) throw std::runtime_error("Instrumented sweep log write/flush failed: "+std::string(revision));
}

inline std::string trail_probe_channels_text(const std::vector<std::uint8_t>& pixels,unsigned offset,unsigned channels) {
    std::string text;
    for(unsigned c=0;c<channels;++c) text+=(c ? "," : "")+std::to_string(pixels.at(offset+c));
    return text;
}

inline void write_dash_probe_sweep_read(TrailProbeRead phase,const std::vector<std::uint8_t>& pixels,const char* revision,unsigned frame,FILE* log) {
    const auto name=trail_probe_read_name(phase);const auto channels=trail_probe_channels(phase);
    if(pixels.size()!=512*512*channels || !revision || !*revision || !log) throw std::invalid_argument("Instrumented sweep requires exact RGB/RGBA bytes, revision and log");
    if(phase==TrailProbeRead::original_post_mask) write_dash_probe_diagnostic(pixels,revision,frame,log);
    if(phase==TrailProbeRead::marker_rgba || phase==TrailProbeRead::marker_rgb) {
        const auto path=std::string("ux0:data/celeste_native_room-")+revision+(phase==TrailProbeRead::marker_rgba ?
            "-dash-probe-diagnostic-markers.trail.rgba" : "-dash-probe-diagnostic-markers.trail.rgb");
        write_guest_file(path.c_str(),std::string_view(reinterpret_cast<const char*>(pixels.data()),pixels.size()),SCE_O_EXCL);
    }
    const auto counts=trail_probe_read_counts(pixels,trail_probe_sentinel(phase));std::string histogram;
    for(auto count:counts.histogram) histogram+=(histogram.empty() ? "" : ",")+std::to_string(count);
    write_dash_probe_sweep_event("read phase="+std::string(name)+" format="+(channels==3 ? "RGB" : "RGBA")+" width=512 height=512 channels="+
        std::to_string(channels)+" bytes="+std::to_string(pixels.size())+" sentinel="+std::to_string(trail_probe_sentinel(phase))+
        " changed_bytes="+std::to_string(counts.changed)+" sentinel_retained_bytes="+std::to_string(counts.retained)+" zero_bytes="+std::to_string(counts.zero)+
        " legacy_zero_initialized="+std::to_string(phase==TrailProbeRead::original_post_mask)+" histogram16="+histogram,revision,frame,log);
    if(phase==TrailProbeRead::original_post_mask) return;
    const auto sample=[&](const char* point,unsigned x,unsigned top,const std::string& expected) {
        const unsigned row=511-top,offset=(row*512+x)*channels,mirror=(top*512+x)*channels;
        write_dash_probe_sweep_event("sample phase="+std::string(name)+" point="+point+" channels="+std::to_string(channels)+
            " x="+std::to_string(x)+" top="+std::to_string(top)+" row="+std::to_string(row)+" offset="+std::to_string(offset)+
            " expected_rgba="+expected+" actual="+trail_probe_channels_text(pixels,offset,channels)+" mirrored_row="+std::to_string(top)+
            " mirrored_offset="+std::to_string(mirror)+" mirrored="+trail_probe_channels_text(pixels,mirror,channels),revision,frame,log);
    };
    if(phase==TrailProbeRead::marker_rgba || phase==TrailProbeRead::marker_rgb) {
        for(const auto& marker:trail_probe_markers) {
            const auto& c=marker.rgba;
            sample(marker.name,marker.x+2,marker.top+2,std::to_string(c[0])+","+std::to_string(c[1])+","+std::to_string(c[2])+","+std::to_string(c[3]));
        }
    } else {
        constexpr unsigned pre_mask[4][4]{{64,32,16,128},{96,48,24,192},{51,120,0,255},{16,16,16,64}};
        for(unsigned i=0;i<4;++i) {
            const auto& point=trail_probe_swatches[i];std::string expected;
            for(unsigned c=0;c<4;++c) expected+=(c ? "," : "")+std::to_string(phase==TrailProbeRead::pre_mask ? pre_mask[i][c] : point.expected);
            sample(point.name,point.x,point.top,expected);
        }
    }
}

}
