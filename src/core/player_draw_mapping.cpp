#include "player_draw_mapping.hpp"
#include <set>
#include <stdexcept>

namespace celeste {
std::vector<LogicalPlayerFrame> read_player_draw_mapping(std::istream& stream,const PlayerFrameBank& bank) {
    std::string magic;
    unsigned count=0;
    if(!(stream>>magic>>count) || magic!="CPLAYERDRAW1" || count!=bank.frames.size() || !count)
        throw std::invalid_argument("Invalid Player draw mapping header");
    std::vector<LogicalPlayerFrame> mapping;
    std::set<std::string> aliases;
    for(const auto& frame:bank.frames) {
        unsigned page=0;
        int u,v,width,height,tx,ty,fw,fh;
        LogicalPlayerFrame logical;
        if(!(stream>>logical.name>>page>>u>>v>>width>>height>>tx>>ty>>fw>>fh>>logical.sheet
             >>logical.sheet_width>>logical.sheet_height>>logical.x>>logical.y>>logical.width>>logical.height))
            throw std::invalid_argument("Incomplete Player draw mapping");
        if(logical.name!=frame.name || !aliases.insert(logical.name).second || page!=frame.page || u!=frame.u || v!=frame.v ||
           width!=frame.width || height!=frame.height || tx!=frame.trim_x || ty!=frame.trim_y ||
           fw!=frame.frame_width || fh!=frame.frame_height || width<0 || height<0 ||
           logical.sheet.empty() || logical.sheet.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/")!=std::string::npos ||
           logical.sheet_width<=0 || logical.sheet_height<=0 || logical.x<0 || logical.y<0 ||
           logical.width!=width || logical.height!=height || logical.x>logical.sheet_width-width || logical.y>logical.sheet_height-height)
            throw std::invalid_argument("Player draw mapping alias/trim/rectangle mismatch");
        mapping.push_back(std::move(logical));
    }
    std::string extra;
    if(stream>>extra) throw std::invalid_argument("Trailing Player draw mapping");
    if(!stream.eof()) throw std::runtime_error("Failed reading Player draw mapping");
    return mapping;
}
}
