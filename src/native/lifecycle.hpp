#pragma once

#include "player.hpp"
#include "presentation.hpp"
#include "trails.hpp"

namespace celeste {

struct LifecycleStats {
    unsigned jumps=0, session_deaths=0, room_deaths=0, save_deaths=0;
    unsigned reloads=0, loads=0, respawn_callbacks=0, wipe_callbacks=0;
    unsigned corpse_adds=0, corpse_commits=0, corpse_removes=0, particle_clears=0;
    unsigned scoped_room_random_calls=0;
    std::int64_t session_time=0;
    bool timer_started=false, hit_checkpoint=false;
};

struct LifecycleRandomEvent {
    std::string phase, operation;
    unsigned calls;
};

struct LifecycleCallback {
    std::string name;
    int state_before=0, state_after=0;
    Vec2 scale{};
    float max_fall=0, time_left=0, percent=0;
    bool completed=false, ending=false;
};

struct WipeVertex { Vec2 position; PresentationColor color{0,0,0,255}; };

class AngledWipe final {
public:
    explicit AngledWipe(bool wipe_in) : wipe_in(wipe_in) {}
    const bool wipe_in;
    float percent=0;
    bool completed=false, ending=false;
    bool update(float raw_delta_time);
    std::array<WipeVertex,36> vertices() const;
};

struct DustParticle {
    Vec2 position, speed;
    int source;
    float size, life, rotation, spin;
};

class FirstRoomSession final {
public:
    FirstRoomSession(const PlayerWorld& world, const PlayerFrameBank& bank, bool hit_checkpoint=false,
                     std::int32_t diagnostic_seed=0);
    FirstRoomSession(const FirstRoomSession&)=delete;
    FirstRoomSession& operator=(const FirstRoomSession&)=delete;
    void step(float raw_delta_time, PlayerInput input);
    std::vector<PlayerDraw> draw();
    const Player& player() const { return *player_; }
    PlayerPresentation& presentation() { return *presentation_; }
    const PlayerPresentation& presentation() const { return *presentation_; }
    const PlayerFrameContext& context() const { return context_; }
    const PresentationRandom& random() const { return random_; }
    const PlayerWorld& world() const { return world_; }
    const LifecycleStats& stats() const { return stats_; }
    const std::vector<LifecycleRandomEvent>& random_events() const { return random_events_; }
    const std::vector<LifecycleCallback>& callbacks() const { return callbacks_; }
    bool pending_corpse() const { return corpse_ && !corpse_committed_; }
    bool committed_corpse() const { return corpse_ && corpse_committed_; }
    float time_active() const { return time_active_; }
    float raw_time_active() const { return raw_time_active_; }
    Vec2 camera() const { return camera_; }
    Vec2 shake() const { return shake_; }
    const AngledWipe* wipe() const { return wipe_.get(); }
    PlayerProjection projection() const;
    const char* phase() const;
    float effect_percent() const;
    float corpse_tween_time() const;
    float buffer_before_scene() const { return buffer_before_scene_; }
    bool pressed_before_scene() const { return pressed_before_scene_; }
    bool scene_ran() const { return scene_ran_; }
    bool foreground_owner() const { return foreground_owner_; }
    const std::vector<DustParticle>& dust() const { return dust_; }
    PlayerTrails& trails() { return trails_; }
    const PlayerTrails& trails() const { return trails_; }
private:
    struct Corpse;
    const PlayerFrameBank& bank_;
    const std::int32_t diagnostic_seed_;
    const PlayerWorld initial_world_;
    Vec2 retained_solid_position_{};
    const TileGrid* retained_grid_=nullptr;
    std::vector<StaticSpike> spike_definitions_, spikes_;
    PlayerWorld world_;
    PlayerFrameContext context_;
    PresentationRandom random_;
    float time_active_=0, raw_time_active_=0, shake_timer_=0, buffer_before_scene_=0;
    Vec2 camera_{}, shake_{};
    PlayerInput input_{};
    LifecycleStats stats_;
    std::unique_ptr<Player> player_;
    std::unique_ptr<PlayerPresentation> presentation_;
    PlayerTrails trails_;
    std::shared_ptr<Corpse> corpse_;
    std::shared_ptr<AngledWipe> wipe_;
    bool corpse_committed_=false, wipe_pending_=false, scene_ran_=false, updating_=false;
    bool pressed_before_scene_=false;
    bool foreground_owner_=true;
    std::string random_phase_;
    std::vector<LifecycleRandomEvent> random_events_;
    std::vector<LifecycleCallback> callbacks_;
    std::vector<DustParticle> dust_;
    unsigned dust_index_=0;
    unsigned sweat_frame_=0;
    void load();
    void reload();
    void queue_corpse();
    void commit_corpse();
    void update_corpse();
    void end_corpse();
    void observe(PlayerCosmeticPhase phase);
    void dust_burst(Vec2 position, int count);
};

}
