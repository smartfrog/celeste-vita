#include "player.hpp"
#include <cmath>
#include <stdexcept>

namespace celeste {
void Player::before_up_transition() {
    if(updating_ || death_.dead || machine_.state()==14) throw std::logic_error("Invalid BeforeUpTransition entry");
    if(machine_.state()==2 || state_.dash_attack_timer>0 || clock_.freeze_timer>0)
        throw std::runtime_error("Unsupported Dash/freeze room transition");
    state_.speed.x=0;
    state_.var_jump_speed=state_.speed.y=-105;
    machine_.set_state(0);
    state_.auto_jump=true;
    state_.auto_jump_timer=0;
    state_.var_jump_timer=0.2f;
    state_.dash_cooldown_timer=0.2f;
}

bool Player::transition_to(Vec2 target,float delta_time) {
    if(updating_ || death_.dead) throw std::logic_error("Invalid Player transition update");
    if(!std::isfinite(delta_time) || delta_time<0 || !std::isfinite(60.f*delta_time))
        throw std::invalid_argument("Invalid transition delta");
    actor_.move_towards(target,60.f*delta_time);
    if(actor_.body.position.x!=target.x || actor_.body.position.y!=target.y) return false;
    actor_.zero_remainder();
    state_.speed={float(round_to_even(state_.speed.x)),float(round_to_even(state_.speed.y))};
    return true;
}

void Player::on_transition() {
    if(updating_ || death_.dead) throw std::logic_error("Invalid OnTransition entry");
    state_.wall_slide_timer=1.2f;
    state_.jump_grace_timer=0;
    state_.force_move_x_timer=0;
    state_.dashes=1;
    state_.stamina=110;
}

bool Player::ground_query() const { return on_ground(actor_.body.position); }
}
