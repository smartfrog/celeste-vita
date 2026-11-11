#pragma once
#include <array>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace celeste::diagnostic {

enum class TrailProbeRead { pre_mask,original_post_mask,paired_a,paired_b,marker_rgba,marker_rgb };
inline const char* trail_probe_read_name(TrailProbeRead phase) {
    switch(phase) {
    case TrailProbeRead::pre_mask:return "pre_mask";
    case TrailProbeRead::original_post_mask:return "original_post_mask";
    case TrailProbeRead::paired_a:return "paired_a";
    case TrailProbeRead::paired_b:return "paired_b";
    case TrailProbeRead::marker_rgba:return "marker_rgba";
    case TrailProbeRead::marker_rgb:return "marker_rgb";
    }
    throw std::invalid_argument("Unknown instrumented trail read phase");
}
inline unsigned trail_probe_channels(TrailProbeRead phase) {return phase==TrailProbeRead::marker_rgb ? 3u : 4u;}
inline std::uint8_t trail_probe_sentinel(TrailProbeRead phase) {
    if(phase==TrailProbeRead::original_post_mask) return 0;
    if(phase==TrailProbeRead::pre_mask) return 0xc3;
    return phase==TrailProbeRead::paired_b || phase==TrailProbeRead::marker_rgb ? 0x5a : 0xa5;
}
struct TrailProbeReadCounts {
    unsigned changed=0,retained=0,zero=0;
    std::array<unsigned,16> histogram{};
};
inline TrailProbeReadCounts trail_probe_read_counts(const std::vector<std::uint8_t>& pixels,std::uint8_t sentinel) {
    TrailProbeReadCounts counts;
    for(auto byte:pixels) {
        counts.changed+=byte!=sentinel;counts.retained+=byte==sentinel;counts.zero+=byte==0;
        ++counts.histogram[byte>>4];
    }
    return counts;
}
struct TrailProbePairCounts {unsigned retained_pairs=0,differing=0;const char* classification;};
inline TrailProbePairCounts trail_probe_pair_counts(const std::vector<std::uint8_t>& first,const std::vector<std::uint8_t>& second) {
    if(first.empty() || first.size()!=second.size()) throw std::invalid_argument("Sentinel pair requires equal nonempty buffers");
    TrailProbePairCounts counts{};
    for(unsigned i=0;i<first.size();++i) {
        counts.retained_pairs+=first[i]==0xa5 && second[i]==0x5a;
        counts.differing+=first[i]!=second[i];
    }
    counts.classification=counts.retained_pairs==first.size() ? "no_write" : counts.retained_pairs ? "partial_no_write" :
        counts.differing ? "differing_reads" : "consistent_overwrite";
    return counts;
}
struct TrailProbeMarker {
    const char* name;
    unsigned x,top,width,height;
    std::array<std::uint8_t,4> rgba;
    bool scissored;
};
inline constexpr TrailProbeMarker trail_probe_markers[]{
    {"clear",448,448,64,64,{17,33,65,96},true},
    {"scissored_quad",452,452,12,12,{68,119,170,255},true},
    {"unscissored_quad",484,484,12,12,{205,82,41,255},false}};

}
