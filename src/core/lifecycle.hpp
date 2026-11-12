#pragma once

#include "player.hpp"
#include "presentation.hpp"
#include "trails.hpp"
#include "rooms.hpp"
#include <deque>

namespace celeste {

struct LifecycleStats {
    unsigned jumps=0, session_deaths=0, room_deaths=0, save_deaths=0;
    unsigned reloads=0, loads=0, respawn_callbacks=0, wipe_callbacks=0;
    unsigned corpse_adds=0, corpse_commits=0, corpse_removes=0, particle_clears=0;
    unsigned scoped_room_random_calls=0;
    unsigned session_dashes=0,save_dashes=0;
    std::int64_t session_time=0;
    std::int64_t save_time=0;
    bool timer_started=false, hit_checkpoint=false;
};

struct LifecycleRandomEvent {
    std::string phase, operation;
    unsigned calls;
    std::string room{};
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
enum class SessionPhase { before_frame,before_update,before_eof,after_eof,after_frame };
struct RoomRosterEntry {
    const RoomRuntime* room=nullptr;
    RoomEntity* entity=nullptr;
    const Player* player=nullptr;
};
struct RoomTransition {
    const std::uint64_t object_identity=next_object_identity();
    const RoomDefinition* destination;
    Coroutine routine;
    bool loaded=false,complete=false,camera_finished=false;
    float camera_at=0;
    Vec2 camera_from{},camera_to{},player_to{};
    std::vector<const RoomEntity*> outgoing;
    explicit RoomTransition(const RoomDefinition* destination) : destination(destination) {}
};
struct ChaserSample { float timestamp; Vec2 position,speed; int facing; };

class FirstRoomSession final {
public:
    FirstRoomSession(const PlayerWorld& world, const PlayerFrameBank& bank, bool hit_checkpoint=false,
                     std::int32_t diagnostic_seed=0,const RoomCatalog* catalog=nullptr);
    FirstRoomSession(const FirstRoomSession&)=delete;
    FirstRoomSession& operator=(const FirstRoomSession&)=delete;
    void step(float raw_delta_time, PlayerInput input,std::function<void(SessionPhase,const FirstRoomSession&)> observer={});
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
    const RoomDefinition* room_definition() const { return current_room_ ? &current_room_->definition : nullptr; }
    const RoomTransition* transition() const { return transition_.get(); }
    bool owns_outgoing_room() const { return bool(outgoing_room_); }
    bool pending_end_of_frame() const { return pending_room_!=nullptr; }
    const std::optional<RoomBounds>& previous_bounds() const { return previous_bounds_; }
    Vec2 respawn_point() const { return respawn_point_; }
    const std::vector<RoomRosterEntry>& room_roster() const { return room_roster_; }
    std::vector<const RoomEntity*> pending_room_entities() const;
    const std::deque<ChaserSample>& chaser_history() const { return chaser_history_; }
    float next_transition_duration() const { return next_transition_duration_; }
    std::uint64_t object_identity() const { return object_identity_; }
private:
    const std::uint64_t object_identity_=next_object_identity();
    struct Corpse;
    const PlayerFrameBank& bank_;
    const std::int32_t diagnostic_seed_;
    const PlayerWorld initial_world_;
    const RoomCatalog* catalog_;
    std::unique_ptr<RoomRuntime> current_room_,outgoing_room_,incoming_room_;
    std::unique_ptr<RoomTransition> transition_;
    const RoomDefinition* pending_room_=nullptr;
    std::optional<RoomBounds> previous_bounds_;
    Vec2 respawn_point_{19,144};
    float next_transition_duration_=0.65f;
    std::vector<RoomRosterEntry> room_roster_;
    std::deque<ChaserSample> chaser_history_;
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
    void load();
    void reload();
    void queue_corpse();
    void commit_corpse();
    void update_corpse();
    void end_corpse();
    void observe(PlayerCosmeticPhase phase);
    void dust_burst(Vec2 position, int count);
    void bind_room_world();
    void publish_room_roster();
    void enforce_room_bounds();
    void start_room_transition();
    void update_room_transition();
    IteratorStep transition_step();
};

}
