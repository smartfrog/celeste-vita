#include "decal_commands.hpp"
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace celeste::decal_commands {
DecalGeometry project_geometry(const DecalCommand& command,int sheet_width,int sheet_height) {
    if(sheet_width<=0 || sheet_height<=0 || command.source_width<0 || command.source_height<0 ||
       command.effects!="None" || !std::isfinite(command.rotation) ||
       !std::isfinite(command.position.x) || !std::isfinite(command.position.y) ||
       !std::isfinite(command.origin.x) || !std::isfinite(command.origin.y) ||
       !std::isfinite(command.scale.x) || !std::isfinite(command.scale.y))
        throw std::invalid_argument("Unsupported logical decal geometry input");
    const float source_x=float(command.source_x)/float(sheet_width);
    const float source_y=float(command.source_y)/float(sheet_height);
    const float source_width=float(command.source_width)/float(sheet_width);
    const float source_height=float(command.source_height)/float(sheet_height);
    const float width=command.scale.x*float(command.source_width);
    const float height=command.scale.y*float(command.source_height);
    const float origin_x=command.origin.x/source_width/float(sheet_width);
    const float origin_y=command.origin.y/source_height/float(sheet_height);
    const float sine=float(std::sin(double(command.rotation))),cosine=float(std::cos(double(command.rotation)));
    DecalGeometry result;
    unsigned index=0;
    for(const auto corner:{Vec2{0,0},Vec2{1,0},Vec2{0,1},Vec2{1,1}}) {
        const float x=(corner.x-origin_x)*width,y=(corner.y-origin_y)*height;
        const std::array<float,5> vertex{{(0.f-sine)*y+cosine*x+command.position.x,
            cosine*y+sine*x+command.position.y,0.f,corner.x*source_width+source_x,corner.y*source_height+source_y}};
        for(unsigned field=0;field<vertex.size();++field) {
            std::memcpy(&result.vertices[index][field],&vertex[field],sizeof(float));
            result.finite=result.finite && std::isfinite(vertex[field]);
        }
        ++index;
    }
    return result;
}
}
