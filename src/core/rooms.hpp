#pragma once
#include "hazards.hpp"
#include "presentation.hpp"
#include <variant>
#include <memory>

namespace celeste {
namespace draw_order { struct AuthoredDecalOwners; }
struct RoomBounds {
    int x=0,y=0,width=320,height=180;
    bool contains(Vec2 point) const;
};
enum class RoomObjectKind { spike_up, spike_left, jump_thru, spring, strawberry };
struct RoomObjectDefinition {
    RoomObjectKind kind;
    int id;
    Vec2 position;
    int size=0;
};
struct RoomDefinition {
    std::string name;
    RoomBounds bounds;
    int load_seed;
    Vec2 spawn;
    std::vector<RoomObjectDefinition> objects;
};
class RoomCatalog final {
public:
    explicit RoomCatalog(std::vector<RoomDefinition> rooms);
    const RoomDefinition& first() const { return rooms_.front(); }
    const std::vector<RoomDefinition>& definitions() const { return rooms_; }
    const RoomDefinition* at(Vec2 point) const;
private:
    const std::vector<RoomDefinition> rooms_;
};

struct RoomSceneHelper { Vec2 position{}; };
struct RoomWind { Vec2 speed{}; void update(float delta); };
struct RoomJumpThru { Body body; };
std::vector<std::pair<int,int>> choose_jump_thru_cells(const Body& body,PresentationRandom& random,const StaticWorld& collision);
struct RoomSpring {
    Body body;
    Body* attached=nullptr;
    float wiggler=0;
    unsigned updates=0;
};
struct RoomStrawberry {
    Body body;
    float wobble=0, sprite_timer=0, light_y=0;
    unsigned sprite_frame=0, updates=0;
    float light_alpha_multiplier=1;
};
using RoomObject=std::variant<RoomSceneHelper,RoomWind,StaticSpike,RoomJumpThru,RoomSpring,RoomStrawberry>;
class RoomEntity final {
public:
    RoomEntity(int authored_id,RoomObject object);
    const int authored_id;
    const std::uint64_t object_identity=next_object_identity();
    RoomObject object;
    std::vector<std::pair<int,int>> image_cells;
    bool present=true;
    bool active=true;
    unsigned updates=0;
    int tag() const;
    int depth() const;
    Vec2 position() const;
    const Body* body() const;
    bool should_update(bool transitioning) const { return transitioning ? (tag()&4)!=0 : active; }
    void update(float delta);
};
struct BannerState {
    std::uint64_t authored_identity;
    float sine_timer;
};
struct JumpThruVisual {
    std::uint64_t object_identity;
    std::vector<std::pair<int,int>> cells;
};
class RoomRuntime final {
public:
    RoomRuntime(const RoomDefinition& definition,const StaticWorld& collision,bool initial=false,
                const draw_order::AuthoredDecalOwners* visual_owners=nullptr);
    const RoomDefinition& definition;
    std::vector<std::unique_ptr<RoomEntity>> entities;
    PresentationRandom scoped_random;
    std::vector<std::pair<std::string,unsigned>> random_events;
    const std::vector<BannerState>& banners() const { return banners_; }
    float banner_phase(std::uint64_t authored_identity) const;
    const JumpThruVisual& jump_thru_visual(std::uint64_t object_identity) const;
    void update_banners(float delta);
    void update(float delta,bool transitioning);
private:
    std::vector<BannerState> banners_;
    std::vector<JumpThruVisual> jump_thru_visuals_;
};
}
