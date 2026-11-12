#pragma once

#include "player_draw_mapping.hpp"
#include <cmath>
#include <iomanip>
#include <istream>
#include <limits>
#include <ostream>

namespace native_test {
using celeste::LogicalPlayerFrame;
using celeste::read_player_draw_mapping;

inline void write_player_draw(std::ostream& stream, int tick, std::uint64_t owner, bool live,
                              const celeste::PlayerFrameBank& bank, const std::vector<LogicalPlayerFrame>& mapping,
                              const std::vector<celeste::PlayerDraw>& cached) {
    if(mapping.size()!=bank.frames.size() || (live && cached.size()!=2 && cached.size()!=22) || (!live && cached.size()!=40))
        throw std::invalid_argument("Unsupported cached Player command branch");
    for(const auto& command:cached) {
        if(command.frame>=bank.frames.size()) throw std::invalid_argument("Invalid cached Player frame");
        for(float value:{command.position.x,command.position.y,command.origin.x,command.origin.y,command.scale.x,command.scale.y,command.rotation})
            if(!std::isfinite(value)) throw std::invalid_argument("Nonfinite cached Player command");
    }
    const auto vec=[&](celeste::Vec2 value) { stream<<'['<<value.x<<','<<value.y<<']'; };
    stream<<std::setprecision(std::numeric_limits<float>::max_digits10);
    stream<<"{\"event\":\"player-draw\",\"tick\":"<<tick<<",\"player\":"<<owner<<",\"renderCalls\":1,\"commands\":[";
    for(unsigned index=0;index<cached.size();++index) {
        const auto& command=cached[index];
        const auto& frame=bank.frames[command.frame];
        const auto& logical=mapping[command.frame];
        if(index) stream<<',';
        stream<<"{\"index\":"<<index<<",\"owner\":"<<owner<<",\"componentType\":";
        if(!live) stream<<"null";
        else stream<<'"'<<(index+2<cached.size() ? "PlayerHair" : index+2==cached.size() ? "PlayerSprite" : "Sprite")<<'"';
        stream<<",\"attribution\":\"native cached draw branch; not SOURCE component object identity\",\"frame\":"<<command.frame
            <<",\"frameName\":\""<<frame.name<<"\",\"nativeFrame\":["<<frame.page<<','<<frame.u<<','<<frame.v<<','
            <<frame.width<<','<<frame.height<<','<<frame.trim_x<<','<<frame.trim_y<<','<<frame.frame_width<<','<<frame.frame_height
            <<"],\"sheet\":\""<<logical.sheet<<"\",\"dimensions\":["<<logical.sheet_width<<','<<logical.sheet_height
            <<"],\"sourceRectangle\":["<<logical.x<<','<<logical.y<<','<<logical.width<<','<<logical.height<<"],\"position\":";
        vec(command.position);
        stream<<",\"origin\":";vec({command.origin.x-frame.trim_x,command.origin.y-frame.trim_y});
        stream<<",\"scale\":";vec(command.scale);
        stream<<",\"rotation\":"<<command.rotation<<",\"color\":["<<unsigned(command.color.r)<<','<<unsigned(command.color.g)<<','
            <<unsigned(command.color.b)<<','<<unsigned(command.color.a)<<"]}";
    }
    stream<<"]}\n";
    if(!stream) throw std::runtime_error("Failed writing cached Player commands");
}
}
