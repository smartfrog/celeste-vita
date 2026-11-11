#pragma once

#include "presentation.hpp"

namespace celeste {

struct TrailSnapshot {
    Vec2 position{}, scale{};
    PresentationColor color{68,183,255,255};
    float percent=0;
    std::uint64_t order=0;
    bool occupied=false, committed=false, removing=false, drawn=false;
};

class PlayerTrails final {
public:
    static constexpr unsigned capacity=64, tile_size=64, target_size=512;
    using Capture = std::function<void(unsigned,const std::vector<PlayerDraw>&)>;
    int add(const PlayerProjection& player, const PlayerPose& pose);
    void update(float delta_time);
    void before_render(PlayerPresentation& presentation, const PlayerProjection& player, const Capture& capture);
    void clear();
    std::vector<unsigned> render_order() const;
    const std::array<TrailSnapshot,capacity>& slots() const { return slots_; }
    unsigned count() const;
    unsigned generation() const { return generation_; }
    static PresentationColor faded_color(const TrailSnapshot& snapshot);
private:
    std::array<TrailSnapshot,capacity> slots_{};
    std::uint64_t next_order_=0;
    unsigned generation_=0;
    bool manager_created_=false, manager_committed_=false;
};

}
