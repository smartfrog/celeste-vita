#include "player.hpp"
#include "fixture_io.hpp"

#include <deque>
#include <map>
#include <memory>

using namespace celeste;
using namespace native_test;

namespace {

class PlayerRunner {
public:
    void run(const std::vector<std::string>& f) {
        const auto& op = f.at(0);
        if (op == "case") {
            player_.reset();
            world_ = {};
            bodies_.clear();
            ids_.clear();
            name_ = f.at(1);
            frame_ = 0;
            spawn_ = {parse_float(f.at(2)), parse_float(f.at(3))};
            speed_ = {parse_float(f.at(4)), parse_float(f.at(5))};
            world_.bounds_left = std::stoi(f.at(6));
            world_.bounds_right = std::stoi(f.at(7));
            return;
        }
        if (op == "solid" || op == "jump") {
            if (player_) throw std::invalid_argument("Fixtures must declare static platforms before frames");
            bodies_.push_back({{parse_float(f.at(2)), parse_float(f.at(3))}, Hitbox{parse_float(f.at(4)), parse_float(f.at(5)), {}}, true});
            Body* body = &bodies_.back();
            ids_[body] = std::stoi(f.at(1));
            (op == "solid" ? world_.collision.solids : world_.collision.jump_thrus).push_back(body);
            if (flag(f.at(6))) world_.safe_ground.push_back(body);
            return;
        }
        if (op != "tick") throw std::invalid_argument("Unknown Player operation");
        if (!player_) player_ = std::make_unique<Player>(world_, spawn_, speed_);
        ++frame_;
        delta_ = parse_float(f.at(1));
        input_ = {std::stoi(f.at(2)), std::stoi(f.at(3)),
                  {flag(f.at(4)), flag(f.at(5)), flag(f.at(6)), flag(f.at(7)), false}, flag(f.at(8)), flag(f.at(9))};
        try {
            player_->frame(delta_, input_, [this](const char* phase, const CollisionData* data) { trace(phase, data); });
        } catch (const std::invalid_argument&) { trace("rejected", nullptr); }
    }

private:
    PlayerWorld world_;
    std::deque<Body> bodies_;
    std::map<const Body*, int> ids_;
    std::unique_ptr<Player> player_;
    std::string name_;
    Vec2 spawn_, speed_;
    int frame_ = 0;
    float delta_ = 0.0f;
    PlayerInput input_;

    static bool flag(const std::string& value) {
        if (value != "0" && value != "1") throw std::invalid_argument("Invalid Player flag");
        return value == "1";
    }

    void trace(const char* phase, const CollisionData* data) const {
        const auto& p = *player_;
        const auto& s = p.state();
        const auto pos = p.actor().body.position;
        const auto rem = p.actor().position_remainder();
        const CollisionData d = data ? *data : CollisionData{};
        std::cout << name_ << '\t' << frame_ << '\t' << phase << '\t' << bits(delta_)
                  << '\t' << input_.x << '\t' << input_.y << '\t' << input_.jump.held << '\t' << input_.jump.pressed
                  << '\t' << input_.jump.released << '\t' << input_.jump.disabled << '\t' << input_.grab << '\t' << input_.dash
                  << '\t' << bits(pos.x) << '\t' << bits(pos.y) << '\t' << bits(rem.x) << '\t' << bits(rem.y)
                  << '\t' << bits(s.previous_position.x) << '\t' << bits(s.previous_position.y)
                  << '\t' << bits(s.speed.x) << '\t' << bits(s.speed.y) << '\t' << s.facing << '\t' << s.move_x
                  << '\t' << s.on_ground << '\t' << s.was_on_ground << '\t' << s.on_safe_ground
                  << '\t' << s.ducking << '\t' << (s.ducking ? "duck" : "normal")
                  << '\t' << bits(s.jump_grace_timer) << '\t' << bits(s.var_jump_timer) << '\t' << bits(s.var_jump_speed)
                  << '\t' << bits(s.max_fall) << '\t' << bits(s.wall_slide_timer) << '\t' << s.wall_slide_dir
                  << '\t' << bits(s.wall_speed_retention_timer) << '\t' << bits(s.wall_speed_retained)
                  << '\t' << bits(s.stamina) << '\t' << s.dashes << '\t' << p.state_machine().state()
                  << '\t' << p.state_machine().previous_state() << '\t' << p.state_machine().changed_states
                  << '\t' << bits(p.jump_button().buffer_counter()) << '\t' << p.jump_button().pressed()
                  << '\t' << p.jump_button().consumed() << '\t' << s.launched << '\t' << (d.hit ? ids_.at(d.hit) : -1)
                  << '\t' << bits(d.direction.x) << '\t' << bits(d.direction.y) << '\t' << bits(d.moved.x) << '\t' << bits(d.moved.y)
                  << '\t' << bits(d.target_position.x) << '\t' << bits(d.target_position.y) << '\n';
    }
};

}

int main(int argc, char** argv) { return run_fixture<PlayerRunner>(argc, argv); }
