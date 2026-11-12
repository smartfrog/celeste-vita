#pragma once
#include "asset_text.hpp"
#include "decal_commands.hpp"
#include <cmath>

namespace celeste::atlas_frame_text {
inline bool identity(std::string_view value) {
    return !value.empty() && value.size()<=192 && value.front()!='/' &&
        value.find("..")==std::string_view::npos &&
        value.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/.\\-")==std::string_view::npos;
}
inline void validate(const decal_commands::AtlasFrame& frame) {
    if(frame.sheet.empty() || frame.sheet.size()>64 ||
       frame.sheet.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")!=std::string::npos ||
       !identity(frame.texture) || frame.x<0 || frame.y<0 || frame.width<=0 || frame.height<=0 ||
       frame.x>4096-frame.width || frame.y>4096-frame.height ||
       !std::isfinite(frame.offset_x) || !std::isfinite(frame.offset_y) ||
       std::abs(frame.offset_x)>4096 || std::abs(frame.offset_y)>4096 ||
       frame.frame_width<=0 || frame.frame_height<=0 || frame.frame_width>4096 || frame.frame_height>4096)
        throw std::invalid_argument("Invalid command atlas frame");
}
inline decal_commands::AtlasFrame parse(std::string_view row) {
    using asset_text::take;
    using asset_text::integer;
    decal_commands::AtlasFrame frame;
    frame.sheet=std::string(take(row,' '));
    frame.x=integer(take(row,' '));frame.y=integer(take(row,' '));
    frame.width=integer(take(row,' '));frame.height=integer(take(row,' '));
    frame.offset_x=float(integer(take(row,' ')));frame.offset_y=float(integer(take(row,' ')));
    frame.frame_width=integer(take(row,' '));frame.frame_height=integer(take(row,' '));
    frame.texture=std::string(row);
    validate(frame);
    return frame;
}
}
