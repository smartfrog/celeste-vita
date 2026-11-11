#pragma once
#include "diagnostic.hpp"
#include <stdexcept>
#include <string_view>

namespace celeste::diagnostic {
inline constexpr const char* guest_dash_probe_id="first_room_dash_trails_v1";
inline constexpr unsigned guest_dash_probe_frames=360;
inline Controls dash_probe_controls(unsigned frame,std::string_view scenario="first") {
    if(frame>=guest_dash_probe_frames) throw std::invalid_argument("Dash probe frame outside input fixture");
    if(scenario!="first" && scenario!="repeat" && scenario!="cancel" && scenario!="reload" && scenario!="capacity" && scenario!="fractional")
        throw std::invalid_argument("Unknown dash trail scenario");
    Controls input;
    if(scenario=="capacity" || scenario=="fractional") return input;
    input.up=frame>=40 && frame<60;
    input.square=frame==40 || (scenario=="repeat" && frame==130);
    if(scenario=="repeat" && frame>=130 && frame<150) input.up=true;
    if(scenario=="cancel" || scenario=="reload") { input.up=false;input.right=frame>=40 && frame<60; }
    if(scenario=="cancel") input.cross=frame==46;
    return input;
}
}
