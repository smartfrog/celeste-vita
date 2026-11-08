#include "draw.hpp"
#include <cmath>
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
TexturedQuad spike_quad(const TextureInfo& t, const SpikePiece& p) {
    return {float(p.x),float(p.y),float(p.width),float(p.height),float(p.u)/t.width,float(p.v)/t.height,
            float(p.u+p.width)/t.width,float(p.v+p.height)/t.height};
}
std::array<PlayerVertex,4> decal_vertices(const DecalTexture& t, const DecalInstance& i) {
    const float origin_x = t.frame_width * 0.5f - t.offset_x;
    const float origin_y = t.frame_height * 0.5f - t.offset_y;
    const float left = i.x - origin_x * i.scale_x;
    const float top = i.y - origin_y * i.scale_y;
    const float right = left + t.width * i.scale_x;
    const float bottom = top + t.height * i.scale_y;
    const float u0 = float(t.u) / DecalAssets::page_width;
    const float v0 = float(t.v) / DecalAssets::page_height;
    const float u1 = float(t.u + t.width) / DecalAssets::page_width;
    const float v1 = float(t.v + t.height) / DecalAssets::page_height;
    return {{{left, top, u0, v0}, {right, top, u1, v0}, {right, bottom, u1, v1}, {left, bottom, u0, v1}}};
}
std::array<PlayerVertex,4> player_vertices(const PlayerFrame& f, const PlayerDraw& d) {
    const float source_width=float(f.width)/4096.f, source_height=float(f.height)/4096.f;
    const float origin_x=(d.origin.x-f.trim_x)/source_width/4096.f;
    const float origin_y=(d.origin.y-f.trim_y)/source_height/4096.f;
    const float width=d.scale.x*f.width, height=d.scale.y*f.height;
    const float sine=static_cast<float>(std::sin(static_cast<double>(d.rotation)));
    const float cosine=static_cast<float>(std::cos(static_cast<double>(d.rotation)));
    std::array<PlayerVertex,4> vertices{};
    unsigned i=0;
    for(const auto corner:{Vec2{0,0},Vec2{1,0},Vec2{1,1},Vec2{0,1}}) {
        const float x=(corner.x-origin_x)*width, y=(corner.y-origin_y)*height;
        vertices[i++]={(-sine)*y+cosine*x+d.position.x,cosine*y+sine*x+d.position.y,
                       (float(f.u)+corner.x*f.width)/128.f,(float(f.v)+corner.y*f.height)/64.f};
    }
    return vertices;
}
}
