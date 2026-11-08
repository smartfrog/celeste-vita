#include "draw.hpp"
#include <stdexcept>

namespace celeste::diagnostic {
TexturedQuad body_quad(const TextureInfo& t, Vec2 position, int facing) {
    if (facing != 1 && facing != -1) throw std::invalid_argument("Body facing must be a source mirror direction");
    const float u0 = 1.0f/t.width, u1 = float(1+t.crop_width)/t.width;
    return {position.x+(facing == 1 ? t.trim_x-16 : 16-t.trim_x-t.crop_width),position.y+t.trim_y-32,
            float(t.crop_width),float(t.crop_height),facing == 1 ? u0 : u1,1.0f/t.height,
            facing == 1 ? u1 : u0,float(1+t.crop_height)/t.height};
}
TexturedQuad tile_quad(const TextureInfo& t, const TileCommand& c) {
    return {float(c.x),float(c.y),8,8,float(1+c.u)/t.width,float(1+c.v)/t.height,
            float(9+c.u)/t.width,float(9+c.v)/t.height};
}
}
