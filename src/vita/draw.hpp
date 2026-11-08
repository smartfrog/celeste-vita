#pragma once
#include "assets.hpp"

namespace celeste::diagnostic {
struct TexturedQuad {
    float x, y, width, height, u0, v0, u1, v1;
};
TexturedQuad body_quad(const TextureInfo& texture, Vec2 position, int facing);
TexturedQuad tile_quad(const TextureInfo& texture, const TileCommand& command);
void initialize_graphics();
void load_textures(const VisualAssets& visuals);
std::string draw(const Room& room, const Player& player, const char* export_path = nullptr, unsigned frame = 0, unsigned resets = 0,
                 const VisualAssets* visuals = nullptr);
void finish_graphics();
}
