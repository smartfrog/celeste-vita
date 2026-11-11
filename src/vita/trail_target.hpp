#pragma once
#include "trails.hpp"
#include <functional>
#ifdef CELESTE_ROOM_DASH_PROBE
#include "trail_probe_diagnostics.hpp"
#endif

namespace celeste::diagnostic {

struct TrailProbeSwatch {const char* name;unsigned x,top,expected;};
inline constexpr TrailProbeSwatch trail_probe_swatches[]{
    {"single",454,454,128},{"inner_union",462,454,192},{"opaque",486,454,255},{"orientation",486,470,64}};

#ifdef CELESTE_ROOM_DASH_PROBE
using TrailProbeReadback=std::function<void(TrailProbeRead,const std::vector<std::uint8_t>&)>;
#endif

class TrailTarget final {
public:
    TrailTarget()=default;
    TrailTarget(const TrailTarget&)=delete;
    TrailTarget& operator=(const TrailTarget&)=delete;
    void capture(PlayerTrails& trails, PlayerPresentation& presentation, const PlayerProjection& player,
                 const PlayerTrails::Capture& draw);
    void render(const PlayerTrails& trails) const;
    std::vector<std::uint8_t> read_rgba() const;
    std::string prepare_probe(const PlayerTrails& trails,const std::function<void(const std::vector<std::uint8_t>&)>& diagnostic,
                              const std::function<void()>& before_mask={});
#ifdef CELESTE_ROOM_DASH_PROBE
    [[noreturn]] void diagnostic_sweep(const PlayerTrails& trails,const TrailProbeReadback& observe,const std::function<void(const std::string&)>& report);
#endif
    void render_probe() const;
    void dispose();
    unsigned texture() const { return texture_; }
private:
    unsigned texture_=0, framebuffer_=0;
    void allocate();
#ifdef CELESTE_ROOM_DASH_PROBE
    std::vector<std::uint8_t> read_probe_pixels(TrailProbeRead phase) const;
#endif
};

}
