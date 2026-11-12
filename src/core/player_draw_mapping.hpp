#pragma once
#include "presentation.hpp"
#include <istream>

namespace celeste {
struct LogicalPlayerFrame {
    std::string sheet;
    int sheet_width=0,sheet_height=0,x=0,y=0,width=0,height=0;
    std::string name={};
};
std::vector<LogicalPlayerFrame> read_player_draw_mapping(std::istream& stream,const PlayerFrameBank& bank);
}
