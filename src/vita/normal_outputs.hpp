#pragma once
#include "guest_io.hpp"
#include "guest_record.hpp"
#include <array>
#include <cstdint>

namespace celeste::diagnostic {

inline constexpr unsigned normal_output_candidates=32;

inline bool normal_record_field(std::string_view record,std::string_view key,std::string_view value) {
    unsigned matches=0;
    while(!record.empty()) {
        const auto end=record.find_first_of(" \n");
        const auto field=record.substr(0,end);
        if(field.substr(0,key.size())==key) {
            if(field.substr(key.size())!=value) return false;
            ++matches;
        }
        if(end==std::string_view::npos) break;
        record.remove_prefix(end+1);
    }
    return matches==1;
}

struct NormalOutputPaths {
    std::string revision,run_id,log,ready,frame,sidecar,failure;
    std::array<std::string,5> destinations() const { return {log,ready,frame,sidecar,failure}; }
    std::string capture_identity() const { return "run_id="+run_id+" capture_outcome=fresh_closed instrumented=1"; }
    std::string record(const char* event,const char* outcome) const {
        return bounded_guest_record<512>("Normal output record exceeds bound",
            "%s run_id=%s revision=%s capture=initial_respawn capture_outcome=%s instrumented=1\n",
            event,run_id.c_str(),revision.c_str(),outcome);
    }
    void validate_capture(const char* path,std::string_view source_revision) const {
        if(!path || frame!=path || revision!=source_revision)
            throw std::runtime_error("Normal capture run/revision/path binding mismatch");
    }
    void confirm_export(std::string_view receipt,std::string_view source_revision) const {
        if(revision!=source_revision || receipt.substr(0,12)!="frame_saved " || receipt.empty() || receipt.back()!='\n' ||
           !normal_record_field(receipt,"path=",frame) || !normal_record_field(receipt,"revision=",revision) ||
           !normal_record_field(receipt,"run_id=",run_id) || !normal_record_field(receipt,"capture=","initial_respawn") ||
           !normal_record_field(receipt,"capture_outcome=","fresh_closed"))
            throw std::runtime_error("Normal closed export run/revision binding mismatch");
    }
};

inline NormalOutputPaths normal_output_paths(std::string_view revision,std::uint64_t token,unsigned candidate) {
    if(revision.empty() || revision.size()>192 || revision.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")!=std::string_view::npos)
        throw std::invalid_argument("Invalid bounded normal output revision");
    if(candidate>=normal_output_candidates) throw std::invalid_argument("Invalid normal output candidate");
    const auto run_id=bounded_guest_record<24>("Normal run token exceeds bound","%016llx-%02x",static_cast<unsigned long long>(token),candidate);
    const auto base="ux0:data/celeste_native_room-run-"+run_id;
    NormalOutputPaths paths{std::string(revision),run_id,base+".log",base+".ready",base+".ppm",base+".ppm.txt",base+"-failure.txt"};
    for(const auto& path:paths.destinations())
        if(path.size()>=256 || path.substr(path.find_last_of('/')+1).size()>255)
            throw std::invalid_argument("Normal output exceeds bounded FAT path");
    return paths;
}

inline NormalOutputPaths claim_normal_outputs(std::string_view revision,std::uint64_t token) {
    for(unsigned candidate=0;candidate<normal_output_candidates;++candidate) {
        auto paths=normal_output_paths(revision,token,candidate);
        bool occupied=false;
        for(const auto& path:paths.destinations()) {
            const bool exists=guest_file_exists(path.c_str());
            occupied=occupied || exists;
        }
        if(occupied) continue;
        write_guest_file(paths.log.c_str(),paths.record("normal_run_claimed","pending"),SCE_O_EXCL);
        return paths;
    }
    throw std::runtime_error("Normal output namespace exhausted for token="+normal_output_paths(revision,token,0).run_id);
}

}
