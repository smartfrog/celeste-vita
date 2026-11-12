#include "presentation.hpp"
#include "player.hpp"

namespace celeste {
PlayerProjection project_player(const Player& player, const PlayerWorld& world, const PlayerInput& input) {
    const auto& s=player.state();
    PlayerProjection p;
    p.position=player.actor().body.position; p.speed=s.speed; p.dash_direction=s.dash_dir;
    p.facing=s.facing; p.state=player.state_machine().state(); p.move_x=s.move_x;
    p.raw_x=input.x; p.raw_y=input.y; p.climb_move=s.last_climb_move; p.wall_slide=s.wall_slide_dir;
    p.dashes=s.dashes; p.on_ground=s.on_ground; p.ducking=s.ducking;
    p.stamina=s.stamina; p.climb_no_move_timer=s.climb_no_move_timer;
    p.dash_attacking=s.dash_attack_timer>0; p.tired=player.tired();
    p.solid_body=[&](Vec2 at){return world.collision.first_solid(player.actor().body,at)!=nullptr;};
    p.solid_point=[&](Vec2 at){return world.collision.solid_at_point(at);};
    p.jump_thru_body=[&](Vec2 at){
        for(const auto* target:world.collision.jump_thrus) if(collide_check(player.actor().body,*target,at)) return true;
        return false;
    };
    return p;
}
}
