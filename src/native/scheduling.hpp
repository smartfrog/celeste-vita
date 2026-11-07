#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <variant>
#include <vector>

namespace celeste {

class Iterator;
using IteratorPtr = std::shared_ptr<Iterator>;
using Yield = std::variant<std::monostate, std::int32_t, float, IteratorPtr>;
using IteratorStep = std::optional<Yield>;

class Iterator final {
public:
    explicit Iterator(std::function<IteratorStep()> next);
    IteratorStep next();
private:
    std::function<IteratorStep()> next_;
};

class Coroutine final {
public:
    explicit Coroutine(bool remove_on_complete = true);
    explicit Coroutine(IteratorPtr iterator, bool remove_on_complete = true);
    Coroutine(const Coroutine&) = delete;
    Coroutine& operator=(const Coroutine&) = delete;

    bool active = false;
    bool remove_on_complete;
    bool use_raw_delta_time = false;

    bool finished() const { return finished_; }
    float wait_timer() const { return wait_timer_; }
    bool ended() const { return ended_; }
    std::size_t stack_depth() const { return stack_.size(); }
    std::size_t removal_events() const { return removal_events_; }
    void update(float delta_time, float raw_delta_time);
    void cancel();
    void replace(IteratorPtr iterator);

private:
    std::vector<IteratorPtr> stack_;
    float wait_timer_ = 0.0f;
    bool finished_ = false;
    bool ended_ = false;
    bool updating_ = false;
    std::size_t removal_events_ = 0;
};

struct StateCallbacks {
    std::function<int()> update;
    std::function<IteratorPtr()> coroutine;
    std::function<void()> begin;
    std::function<void()> end;
};

class StateMachine final {
public:
    explicit StateMachine(int max_states = 10);
    StateMachine(const StateMachine&) = delete;
    StateMachine& operator=(const StateMachine&) = delete;

    bool changed_states = false;
    bool locked = false;
    int state() const { return state_; }
    int previous_state() const { return previous_state_; }
    Coroutine& coroutine() { return coroutine_; }
    const Coroutine& coroutine() const { return coroutine_; }
    void set_callbacks(int state, StateCallbacks callbacks);
    void set_state(int state);
    void force_state(int state);
    void added(bool entity_has_scene);
    void entity_added();
    void update(float delta_time, float raw_delta_time);

private:
    int state_ = -1;
    int previous_state_ = -1;
    std::vector<std::shared_ptr<StateCallbacks>> callbacks_;
    Coroutine coroutine_{false};
    void validate_state(int state) const;
    void transition(int state);
};

}
