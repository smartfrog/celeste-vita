#pragma once
#include "assets.hpp"
#include "command_submission.hpp"
#include "lifecycle.hpp"

namespace celeste::diagnostic {
struct NormalOutputPaths;
struct TexturedQuad {
    float x, y, width, height, u0, v0, u1, v1;
};
TexturedQuad body_quad(const TextureInfo& texture, Vec2 position, int facing);
TexturedQuad tile_quad(const TextureInfo& texture, const TileCommand& command);
TexturedQuad spike_quad(const TextureInfo& texture, const SpikePiece& piece);
struct PlayerVertex { float x, y, u, v; };
std::array<PlayerVertex,4> player_vertices(const PlayerFrame& frame, const PlayerDraw& draw);
std::array<PlayerVertex,4> decal_vertices(const DecalTexture& texture, const DecalInstance& instance);
struct PlayerRender {
    const PlayerAssets& assets;
    PlayerPresentation& presentation;
    const PlayerProjection& projection;
    FirstRoomSession* lifecycle=nullptr;
    PlayerTrails* trails=nullptr;
};
void initialize_graphics();
void require_graphics_ok(const char* stage);
void upload_bounded_rgba(unsigned texture,int width,int height,std::string_view pixels);
// Inactive opt-in entry: no uploads, clear, swap or app wiring. Caller owns the
// current render target/context and verified page pixels; leaves configured draw state.
// Establishes unit-zero-only 2D texturing, no sampler override and an identity UV matrix.
void submit_ready_frame(const command_preflight::ReadyFrame& frame,
                        const std::vector<command_submission::UploadedPage>& pages,
                        const command_submission::View& view);
void load_textures(const VisualAssets& visuals);
void load_decal_textures(const DecalAssets& decals);
void load_player_textures(const PlayerAssets& assets);
std::string draw(const Room& room, const Player& player, const char* export_path = nullptr, unsigned frame = 0, unsigned resets = 0,
                 const VisualAssets* visuals = nullptr, PlayerRender* animated = nullptr, const DecalAssets* decals = nullptr,
                 const NormalOutputPaths* normal_outputs = nullptr);
void finish_graphics();
}
