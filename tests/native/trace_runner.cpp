#include "movement.hpp"

#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>

using namespace celeste;

namespace {

float parse_float(const std::string& text) {
    if (text.at(0) == '@') {
        const auto value = static_cast<std::uint32_t>(std::stoul(text.substr(1), nullptr, 16));
        float result;
        std::memcpy(&result, &value, sizeof(result));
        return result;
    }
    std::size_t consumed;
    const float value = std::stof(text, &consumed);
    if (consumed != text.size()) throw std::invalid_argument("Invalid float: " + text);
    return value;
}

std::string bits(float value) {
    std::uint32_t raw;
    std::memcpy(&raw, &value, sizeof(raw));
    std::ostringstream output;
    output << std::hex << std::setfill('0') << std::setw(8) << raw;
    return output.str();
}

class FixtureRunner {
public:
    void run(const std::vector<std::string>& fields) {
        const std::string& operation = fields.at(0);
        if (operation == "case") {
            name_ = fields.at(1);
            step_ = 0;
            targets_.clear();
            solid_ids_.clear();
            world_ = {};
            actor_ = std::make_unique<Actor>(world_);
        } else if (operation == "actor") {
            configure(actor_->body, fields, 1);
            actor_->ignore_jump_thrus = fields.at(9) == "1";
        } else if (operation == "solid" || operation == "jump") {
            auto body = std::make_unique<Body>();
            configure(*body, fields, 2);
            const int id = std::stoi(fields.at(1));
            if (id <= 0 || targets_.count(id)) throw std::invalid_argument("Duplicate/invalid body ID");
            (operation == "solid" ? world_.solids : world_.jump_thrus).push_back(body.get());
            if (operation == "solid") solid_ids_.insert(id);
            targets_.emplace(id, std::move(body));
        } else if (operation == "self") {
            world_.solids.push_back(&actor_->body);
        } else if (operation == "Q" || operation == "O") {
            ++step_;
            const Vec2 at{parse_float(fields.at(1)), parse_float(fields.at(2))};
            Body* hit = operation == "Q" ? world_.first_solid(actor_->body, at) : world_.first_outside_jump_thru(actor_->body, at);
            CollisionData data;
            data.hit = hit;
            trace("query", hit ? "1" : "0", data);
        } else if (operation == "H" || operation == "V" || operation == "HX" || operation == "VX") {
            ++step_;
            const int pusher_id = std::stoi(fields.at(3));
            if (pusher_id != -1 && !solid_ids_.count(pusher_id)) throw std::invalid_argument("Pusher must be a Solid ID");
            Body* pusher = pusher_id == -1 ? nullptr : targets_.at(pusher_id).get();
            const Collision on_collide = callback(fields.at(2), pusher);
            bool hit;
            if (operation == "H") hit = actor_->move_h(parse_float(fields.at(1)), on_collide, pusher);
            else if (operation == "V") hit = actor_->move_v(parse_float(fields.at(1)), on_collide, pusher);
            else if (operation == "HX") hit = actor_->move_h_exact(std::stoi(fields.at(1)), on_collide, pusher);
            else hit = actor_->move_v_exact(std::stoi(fields.at(1)), on_collide, pusher);
            trace("return", hit ? "1" : "0");
        } else {
            throw std::invalid_argument("Unknown fixture operation: " + operation);
        }
    }

private:
    StaticWorld world_;
    std::unique_ptr<Actor> actor_;
    std::map<int, std::unique_ptr<Body>> targets_;
    std::set<int> solid_ids_;
    std::string name_;
    int step_ = 0;

    void configure(Body& body, const std::vector<std::string>& fields, std::size_t start) {
        body.position = {parse_float(fields.at(start)), parse_float(fields.at(start + 1))};
        body.collider.reset();
        if (fields.at(start + 7) == "1") {
            body.collider = Hitbox{parse_float(fields.at(start + 2)), parse_float(fields.at(start + 3)),
                                  {parse_float(fields.at(start + 4)), parse_float(fields.at(start + 5))}};
        }
        body.collidable = fields.at(start + 6) == "1";
    }

    int id(Body* body) const {
        if (!body) return -1;
        if (body == &actor_->body) return 0;
        for (const auto& pair : targets_) if (pair.second.get() == body) return pair.first;
        throw std::logic_error("Unknown body identity");
    }

    void trace(const char* kind, const char* result, CollisionData data = {}) const {
        const Vec2 position = actor_->body.position;
        const Vec2 remainder = actor_->position_remainder();
        std::cout << name_ << '\t' << step_ << '\t' << kind << '\t' << result
                  << '\t' << bits(position.x) << '\t' << bits(position.y)
                  << '\t' << bits(remainder.x) << '\t' << bits(remainder.y)
                  << '\t' << id(data.hit) << '\t' << id(data.pusher)
                  << '\t' << bits(data.direction.x) << '\t' << bits(data.direction.y)
                  << '\t' << bits(data.moved.x) << '\t' << bits(data.moved.y)
                  << '\t' << bits(data.target_position.x) << '\t' << bits(data.target_position.y) << '\n';
    }

    Collision callback(const std::string& mode, Body* pusher) {
        if (mode == "none") return {};
        if (mode != "record" && mode != "mutate" && mode != "reenterH" && mode != "reenterV") {
            throw std::invalid_argument("Unknown callback mode");
        }
        return [this, mode, pusher](CollisionData data) {
            trace("callback", "-", data);
            if (mode == "mutate") {
                actor_->body.position = {-7.0f, 9.0f};
                actor_->move_h(0.25f);
                actor_->move_v(-0.25f);
            }
            if (mode == "reenterH" || mode == "reenterV") {
                data.hit->collidable = false;
                const bool hit = mode == "reenterH" ? actor_->move_h(1.25f, callback("record", pusher), pusher)
                                                    : actor_->move_v(1.25f, callback("record", pusher), pusher);
                trace("reentry", hit ? "1" : "0");
            }
        };
    }
};

}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::invalid_argument("Expected fixture path");
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("Cannot open fixture file");
        FixtureRunner runner;
        std::string line;
        std::size_t line_number = 0;
        while (std::getline(input, line)) {
            ++line_number;
            std::istringstream tokens(line);
            std::vector<std::string> fields;
            std::string token;
            while (tokens >> token) fields.push_back(token);
            if (fields.empty() || fields.front().at(0) == '#') continue;
            try { runner.run(fields); }
            catch (const std::exception& error) {
                throw std::runtime_error("Fixture line " + std::to_string(line_number) + ": " + error.what());
            }
        }
        if (input.bad()) throw std::runtime_error("Error reading fixture file");
        if (!std::cout) throw std::runtime_error("Error writing trace");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
