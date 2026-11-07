#include "scheduling.hpp"

#include <cmath>
#include <stdexcept>
#include <utility>

namespace celeste {

Iterator::Iterator(std::function<IteratorStep()> next) : next_(std::move(next)) {
    if (!next_) throw std::invalid_argument("Iterator requires a step callback");
}

IteratorStep Iterator::next() { return next_(); }

Coroutine::Coroutine(bool remove) : remove_on_complete(remove) {}

Coroutine::Coroutine(IteratorPtr iterator, bool remove) : Coroutine(remove) {
    if (!iterator) throw std::invalid_argument("Null iterator");
    stack_.push_back(std::move(iterator));
    active = true;
}

void Coroutine::update(float delta_time, float raw_delta_time) {
    if (!std::isfinite(delta_time) || !std::isfinite(raw_delta_time))
        throw std::invalid_argument("Nonfinite delta time");
    if (updating_) throw std::logic_error("Recursive coroutine update is unsupported");
    struct Updating {
        bool& flag;
        explicit Updating(bool& value) : flag(value) { flag = true; }
        ~Updating() { flag = false; }
    } updating(updating_);
    ended_ = false;
    if (wait_timer_ > 0.0f) {
        const float remaining = wait_timer_ - (use_raw_delta_time ? raw_delta_time : delta_time);
        if (!std::isfinite(remaining)) throw std::invalid_argument("Wait timer overflow");
        wait_timer_ = remaining;
        return;
    }
    if (stack_.empty()) return;
    // A step can clear the stack which owns this iterator, including its callback captures.
    const auto iterator = stack_.back();
    const auto step = iterator->next();
    if (ended_) return;
    if (!step) {
        stack_.pop_back();
        if (stack_.empty()) {
            finished_ = true;
            active = false;
            if (remove_on_complete) ++removal_events_;
        }
    } else if (const auto value = std::get_if<std::int32_t>(&*step)) {
        wait_timer_ = static_cast<float>(*value);
    } else if (const auto value = std::get_if<float>(&*step)) {
        if (!std::isfinite(*value)) throw std::invalid_argument("Nonfinite wait yield");
        wait_timer_ = *value;
    } else if (const auto child = std::get_if<IteratorPtr>(&*step)) {
        if (!*child) throw std::invalid_argument("Null child iterator");
        stack_.push_back(*child);
    }
}

void Coroutine::cancel() {
    active = false;
    finished_ = true;
    wait_timer_ = 0.0f;
    stack_.clear();
    ended_ = true;
}

void Coroutine::replace(IteratorPtr iterator) {
    if (!iterator) throw std::invalid_argument("Null replacement iterator");
    active = true;
    finished_ = false;
    wait_timer_ = 0.0f;
    stack_.clear();
    stack_.push_back(std::move(iterator));
    ended_ = true;
}

StateMachine::StateMachine(int max_states) {
    if (max_states <= 0) throw std::invalid_argument("State count must be positive");
    callbacks_.resize(static_cast<std::size_t>(max_states));
}

void StateMachine::validate_state(int state) const {
    if (state < 0 || static_cast<std::size_t>(state) >= callbacks_.size())
        throw std::out_of_range("Invalid state index");
}

void StateMachine::set_callbacks(int state, StateCallbacks callbacks) {
    validate_state(state);
    callbacks_[state] = std::move(callbacks);
}

void StateMachine::set_state(int state) {
    if (locked || state_ == state) return;
    validate_state(state);
    transition(state);
}

void StateMachine::force_state(int state) {
    if (state_ != state) { set_state(state); return; }
    validate_state(state);
    transition(state);
}

void StateMachine::transition(int state) {
    changed_states = true;
    previous_state_ = state_;
    state_ = state;
    if (previous_state_ != -1) {
        const auto end = callbacks_[previous_state_].end;
        if (end) end();
    }
    const auto begin = callbacks_[state_].begin;
    if (begin) begin();
    const auto factory = callbacks_[state_].coroutine;
    if (factory) coroutine_.replace(factory());
    else coroutine_.cancel();
}

void StateMachine::added(bool entity_has_scene) {
    if (entity_has_scene && state_ == -1) set_state(0);
}

void StateMachine::entity_added() {
    if (state_ == -1) set_state(0);
}

void StateMachine::update(float delta_time, float raw_delta_time) {
    validate_state(state_);
    changed_states = false;
    const auto update = callbacks_[state_].update;
    if (update) set_state(update());
    if (coroutine_.active) coroutine_.update(delta_time, raw_delta_time);
}

}
