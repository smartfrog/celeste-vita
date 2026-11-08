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
            grids_.clear();
            ids_.clear();
#ifdef HAZARD_TRACE
            spikes_.clear();
            spike_ids_.clear();
            phases_.clear();
#endif
            name_ = f.at(1);
            frame_ = 0;
            spawn_ = {parse_float(f.at(2)), parse_float(f.at(3))};
            speed_ = {parse_float(f.at(4)), parse_float(f.at(5))};
            world_.bounds_left = std::stoi(f.at(6));
            world_.bounds_right = std::stoi(f.at(7));
            return;
        }
#ifdef HAZARD_TRACE
        if (op == "spike") {
            if (player_) throw std::invalid_argument("Spikes must precede frames");
            if (f.at(5) != "up" && f.at(5) != "left") throw std::invalid_argument("Unsupported spike direction");
            spikes_.emplace_back(Vec2{parse_float(f.at(2)), parse_float(f.at(3))}, std::stoi(f.at(4)),
                                 f.at(5) == "up" ? SpikeDirection::up : SpikeDirection::left, flag(f.at(6)));
            world_.spikes.push_back(&spikes_.back());
            spike_ids_.push_back(f.at(1));
            return;
        }
        if (op == "die") {
            if (!player_) player_ = std::make_unique<Player>(world_, spawn_, speed_);
            ++frame_;
            delta_ = 0;
            phases_.clear();
            operation_ = "die";
            sample_ = bits(parse_float(f.at(1))) + ',' + bits(parse_float(f.at(2)));
            result_ = player_->die({parse_float(f.at(1)), parse_float(f.at(2))}) ? "accepted" : "ignored";
            trace("", nullptr);
            return;
        }
#endif
        if (op == "grid") {
            if (player_) throw std::invalid_argument("Grid must precede frames");
            grids_.push_back(parse_grid(f));
            bodies_.push_back({{parse_float(f.at(2)), parse_float(f.at(3))}, {}, true, grids_.back().get()});
            Body* body = &bodies_.back();
            ids_[body] = std::stoi(f.at(1));
            world_.collision.solids.push_back(body);
            if (flag(f.at(11))) world_.safe_ground.push_back(body);
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
#ifdef DASH_TRACE
        input_.aim_x = std::stoi(f.at(10)); input_.aim_y = std::stoi(f.at(11));
        input_.dash_button = {flag(f.at(12)), flag(f.at(13)), flag(f.at(14)), flag(f.at(7))};
        try {
            player_->frame(delta_, input_, [this](const char* phase, const CollisionData* data) { trace(phase, data); });
        } catch (const std::invalid_argument&) { trace("rejected", nullptr); }
#elif defined(HAZARD_TRACE)
        phases_.clear();
        operation_ = "tick";
        sample_.clear();
        for (std::size_t i = 2; i < 10; ++i) {
            if (!sample_.empty()) sample_ += ',';
            sample_ += f.at(i);
        }
        result_ = "frame";
        try {
            player_->frame(delta_, input_, [this](const char* phase, const CollisionData* data) {
                if (!phases_.empty()) phases_ += ',';
                phases_ += phase;
                if (data) phases_ += ':' + std::to_string(ids_.at(data->hit));
            });
            if (player_->death().dead) result_ = "removed";
        } catch (const std::invalid_argument&) { result_ = "rejected"; }
        trace("", nullptr);
#else
        try {
            player_->frame(delta_, input_, [this](const char* phase, const CollisionData* data) { trace(phase, data); });
        } catch (const std::invalid_argument&) { trace("rejected", nullptr); }
#endif
    }

private:
    PlayerWorld world_;
    std::deque<Body> bodies_;
    std::vector<std::unique_ptr<TileGrid>> grids_;
    std::map<const Body*, int> ids_;
    std::unique_ptr<Player> player_;
    std::string name_;
    Vec2 spawn_, speed_;
    int frame_ = 0;
    float delta_ = 0.0f;
    PlayerInput input_;
#ifdef HAZARD_TRACE
    std::deque<StaticSpike> spikes_;
    std::vector<std::string> spike_ids_;
    std::string phases_, operation_, result_, sample_;

    std::string identities(const std::vector<std::size_t>& indices) const {
        std::string result;
        for (auto i : indices) {
            if (!result.empty()) result += ',';
            result += spike_ids_.at(i);
        }
        return result.empty() ? "-" : result;
    }
#endif

    static bool flag(const std::string& value) {
        if (value != "0" && value != "1") throw std::invalid_argument("Invalid Player flag");
        return value == "1";
    }

    void trace(const char* phase, const CollisionData* data) const {
        const auto& p = *player_;
        const auto& s = p.state();
        const auto pos = p.actor().body.position;
        const auto rem = p.actor().position_remainder();
#ifdef DASH_TRACE
        const CollisionData d = data ? *data : CollisionData{};
        const auto& co = p.state_machine().coroutine();
        const auto& h = p.hazard_frame();
        std::cout << name_ << '\t' << frame_ << '\t' << phase << '\t' << bits(delta_) << '\t' << bits(p.clock().delta) << '\t' << bits(p.clock().freeze_timer) << '\t' << p.clock().frame_counter
            << '\t' << bits(pos.x) << '\t' << bits(pos.y) << '\t' << bits(rem.x) << '\t' << bits(rem.y) << '\t' << bits(s.previous_position.x) << '\t' << bits(s.previous_position.y)
            << '\t' << bits(s.speed.x) << '\t' << bits(s.speed.y) << '\t' << s.facing << '\t' << s.move_x << '\t' << s.on_ground << '\t' << s.was_on_ground
            << '\t' << s.on_safe_ground << '\t' << s.ducking << '\t' << s.dashes << '\t' << p.state_machine().state() << '\t' << p.state_machine().previous_state() << '\t' << p.state_machine().changed_states
            << '\t' << bits(p.jump_button().buffer_counter()) << '\t' << p.jump_button().pressed() << '\t' << p.jump_button().check()
            << '\t' << bits(p.dash_button().buffer_counter()) << '\t' << p.dash_button().pressed() << '\t' << p.dash_button().check() << '\t' << s.started_dashing
            << '\t' << s.dash_started_on_ground << '\t' << s.called_dash_events << '\t' << s.dash_events << '\t' << bits(s.before_dash_speed.x) << '\t' << bits(s.before_dash_speed.y)
            << '\t' << bits(s.dash_dir.x) << '\t' << bits(s.dash_dir.y) << '\t' << bits(s.last_aim.x) << '\t' << bits(s.last_aim.y) << '\t' << bits(s.dash_attack_timer)
            << '\t' << bits(s.dash_cooldown_timer) << '\t' << bits(s.dash_refill_cooldown_timer) << '\t' << bits(s.glider_boost_timer) << '\t' << bits(s.dash_trail_timer) << '\t' << s.dash_trail_counter
            << '\t' << s.auto_jump << '\t' << bits(s.auto_jump_timer) << '\t' << bits(s.jump_grace_timer) << '\t' << bits(s.var_jump_timer) << '\t' << bits(s.var_jump_speed) << '\t' << bits(s.max_fall)
            << '\t' << bits(s.wall_speed_retention_timer) << '\t' << bits(s.wall_speed_retained) << '\t' << p.death().dead << '\t' << (d.hit ? ids_.at(d.hit) : -1)
            << '\t' << bits(d.direction.x) << '\t' << bits(d.direction.y) << '\t' << bits(d.moved.x) << '\t' << bits(d.moved.y) << '\t' << bits(d.target_position.x) << '\t' << bits(d.target_position.y)
            << '\t' << co.active << '\t' << bits(co.wait_timer()) << '\t' << co.ended() << '\t' << co.stack_depth() << '\t' << h.refill_called << '\t' << identities(h.checked) << '\t' << identities(h.overlaps) << '\n';
#elif defined(HAZARD_TRACE)
        (void)phase;
        (void)data;
        const auto& d = p.death();
        const auto& h = p.hazard_frame();
        const auto& box = *p.actor().body.collider;
        const std::string collider = box.height == 11 ? "normal" : box.height == 6 ? "duck" : box.height == 9 ? "hurt_normal" : "hurt_duck";
        std::string events;
        for (auto event : d.events) {
            if (!events.empty()) events += ',';
            events += event == DeathEvent::corpse_created ? "corpse_created" : event == DeathEvent::corpse_added ? "corpse_added" : "player_removed";
        }
        std::cout << name_ << '\t' << frame_ << '\t' << operation_ << '\t' << result_ << '\t' << bits(delta_)
                  << '\t' << bits(pos.x) << '\t' << bits(pos.y) << '\t' << bits(rem.x) << '\t' << bits(rem.y)
                  << '\t' << bits(s.speed.x) << '\t' << bits(s.speed.y) << '\t' << s.ducking << '\t' << collider
                  << '\t' << s.on_ground << '\t' << s.was_on_ground << '\t' << d.dead << '\t' << d.depth
                  << '\t' << p.state_machine().locked << '\t' << p.actor().body.collidable << '\t' << d.removed
                  << '\t' << bits(d.direction.x) << '\t' << bits(d.direction.y) << '\t' << (events.empty() ? "-" : events)
                  << '\t' << h.refill_called << '\t' << identities(h.checked) << '\t' << identities(h.overlaps)
                  << '\t' << (phases_.empty() ? "-" : phases_) << '\t' << s.dashes << '\t' << bits(s.stamina)
                  << '\t' << p.state_machine().state() << '\t' << p.state_machine().previous_state() << '\t' << p.state_machine().changed_states
                  << '\t' << bits(s.previous_position.x) << '\t' << bits(s.previous_position.y)
                  << '\t' << bits(s.jump_grace_timer) << '\t' << bits(s.var_jump_timer) << '\t' << bits(s.var_jump_speed) << '\t' << bits(s.max_fall)
                  << '\t' << sample_ << '\n';
#else
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
#endif
    }
};

}

int main(int argc, char** argv) { return run_fixture<PlayerRunner>(argc, argv); }
