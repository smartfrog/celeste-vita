#include "scheduling.hpp"

#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

using namespace celeste;

namespace {

void expect(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

template<typename Exception, typename Action>
void expect_throws(Action action) {
    try { action(); }
    catch (const Exception&) { return; }
    throw std::runtime_error("Expected exception was not thrown");
}

std::uint32_t bits(float value) {
    std::uint32_t result;
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

IteratorPtr sequence(std::vector<Yield> yields) {
    return std::make_shared<Iterator>([yields = std::move(yields), index = std::size_t{0}]() mutable -> IteratorStep {
        if (index == yields.size()) return std::nullopt;
        return yields[index++];
    });
}

void null_yield_consumes_one_update() {
    Coroutine coroutine(sequence({std::monostate{}}));
    coroutine.update(1.0f, 1.0f);
    expect(coroutine.active && !coroutine.finished() && coroutine.stack_depth() == 1, "Null yield drained iterator");
    coroutine.update(1.0f, 1.0f);
    expect(!coroutine.active && coroutine.finished() && coroutine.stack_depth() == 0, "Iterator did not finish");
}

void wait_crossing_zero_never_resumes_parameterized() {
    for (bool raw : {false, true}) {
        Coroutine coroutine(sequence({0.3f, std::monostate{}}));
        coroutine.use_raw_delta_time = raw;
        coroutine.update(0.2f, 0.4f);
        expect(bits(coroutine.wait_timer()) == bits(0.3f), "Wait yield must not decrement immediately");
        coroutine.update(0.2f, 0.4f);
        const float expected = raw ? 0.3f - 0.4f : 0.3f - 0.2f;
        expect(bits(coroutine.wait_timer()) == bits(expected), "Wait did not use exact selected float32 delta");
        if (!raw) coroutine.update(0.2f, 0.4f);
        expect(coroutine.active && coroutine.stack_depth() == 1, "Zero-crossing tick resumed iterator");
        coroutine.update(0.2f, 0.4f);
        expect(coroutine.active, "Null yield did not consume next tick");
        coroutine.update(0.2f, 0.4f);
        expect(coroutine.finished(), "Wait did not resume on next tick");
    }
}

void zero_negative_integer_waits_parameterized() {
    for (Yield value : {Yield{std::int32_t{0}}, Yield{std::int32_t{-2}}, Yield{-0.0f}, Yield{-0.5f}, Yield{std::int32_t{16777217}}}) {
        Coroutine coroutine(sequence({value, std::monostate{}}));
        coroutine.update(1.0f, 1.0f);
        const float expected = std::holds_alternative<float>(value) ? std::get<float>(value) : static_cast<float>(std::get<std::int32_t>(value));
        expect(bits(coroutine.wait_timer()) == bits(expected), "Wait conversion changed bits");
        coroutine.update(20000000.0f, 20000000.0f);
        expect(coroutine.active, "Nonpositive wait failed to consume a step");
    }
}

void child_push_pop_do_not_step_parent() {
    int calls = 0;
    auto parent = std::make_shared<Iterator>([&, index = 0]() mutable -> IteratorStep {
        ++calls;
        if (index++ == 0) return Yield{sequence({std::monostate{}})};
        return std::nullopt;
    });
    Coroutine coroutine(parent);
    coroutine.update(1, 1);
    expect(calls == 1 && coroutine.stack_depth() == 2, "Child ran on push");
    coroutine.update(1, 1);
    expect(calls == 1 && coroutine.stack_depth() == 2, "Parent ran during child yield");
    coroutine.update(1, 1);
    expect(calls == 1 && coroutine.stack_depth() == 1 && coroutine.active, "Parent resumed on child pop");
    coroutine.update(1, 1);
    expect(calls == 2 && coroutine.finished(), "Parent never resumed");
}

void cancel_and_replace_reset_parameterized() {
    for (bool cancel : {false, true}) {
        Coroutine coroutine(sequence({2.0f}));
        coroutine.update(1, 1);
        if (cancel) coroutine.cancel(); else coroutine.replace(sequence({std::monostate{}}));
        expect(bits(coroutine.wait_timer()) == 0 && coroutine.ended(), "Timer/ended not reset");
        expect(coroutine.active == !cancel && coroutine.finished() == cancel, "Cancel/replace flags");
        expect(coroutine.stack_depth() == (cancel ? 0 : 1), "Cancel/replace stack");
    }
}

void mid_step_replacement_keeps_iterator_alive_parameterized() {
    for (int mode : {0, 1, 2, 3}) {
        Coroutine coroutine(false);
        bool destroyed = false;
        auto token = std::shared_ptr<int>(new int, [&](int* pointer) { destroyed = true; delete pointer; });
        coroutine.replace(std::make_shared<Iterator>([&, token]() -> IteratorStep {
            if (mode < 2) coroutine.cancel(); else coroutine.replace(sequence({0.5f}));
            expect(!destroyed, "Executing iterator destroyed during callback");
            if (mode % 2 == 0) return Yield{99.0f};
            return std::nullopt;
        }));
        token.reset();
        coroutine.update(1, 1);
        expect(destroyed, "Executing iterator leaked after callback");
        expect(bits(coroutine.wait_timer()) == 0 && coroutine.ended(), "Stale yield applied");
        expect(coroutine.stack_depth() == (mode < 2 ? 0 : 1), "Stale completion popped replacement");
        expect(coroutine.active == (mode >= 2), "Replacement active flag lost");
    }
}

void direct_update_ignores_active_flag() {
    Coroutine coroutine(sequence({0.5f}));
    coroutine.active = false;
    coroutine.update(1, 1);
    expect(bits(coroutine.wait_timer()) == bits(0.5f), "Direct Update added an Active guard absent from source");
}

void completion_removal_parameterized() {
    for (bool remove : {false, true}) {
        Coroutine coroutine(sequence({}), remove);
        coroutine.update(1, 1);
        coroutine.update(1, 1);
        expect(coroutine.finished() && !coroutine.active, "Completion flags");
        expect(coroutine.removal_events() == (remove ? 1 : 0), "RemoveOnComplete event count");
    }
}

void attachment_initialization_parameterized() {
    for (int mode : {0, 1, 2}) {
        StateMachine machine;
        expect(machine.state() == -1 && machine.previous_state() == -1, "Initial state fields");
        int begins = 0;
        machine.set_callbacks(0, {{}, {}, [&] { ++begins; }, {}});
        if (mode == 0) machine.added(true);
        if (mode == 1) { machine.added(false); expect(machine.state() == -1, "Added without scene initialized"); machine.entity_added(); }
        if (mode == 2) { machine.set_state(1); machine.entity_added(); }
        expect(machine.state() == (mode == 2 ? 1 : 0), "Attachment overwrote explicit state or failed initialization");
        machine.added(true);
        machine.entity_added();
        expect(begins == (mode == 2 ? 0 : 1), "Attachment repeated transition");
    }
}

void locked_initialization_can_retry() {
    StateMachine machine;
    machine.locked = true;
    machine.entity_added();
    expect(machine.state() == -1, "Attachment bypassed lock");
    machine.locked = false;
    machine.entity_added();
    expect(machine.state() == 0, "Attachment did not retry");
}

void force_and_lock_guards_parameterized() {
    for (bool locked : {false, true}) for (bool same : {false, true}) for (bool force : {false, true}) {
        StateMachine machine;
        int begins = 0;
        machine.set_callbacks(0, {{}, {}, [&] { ++begins; }, {}});
        machine.set_callbacks(1, {{}, {}, [&] { ++begins; }, {}});
        machine.set_state(0);
        machine.changed_states = false;
        machine.locked = locked;
        if (force) machine.force_state(same ? 0 : 1); else machine.set_state(same ? 0 : 1);
        const bool transition = same ? force : !locked;
        expect(machine.changed_states == transition && begins == (transition ? 2 : 1), "Force/lock transition guard");
        expect(machine.state() == ((!same && !locked) ? 1 : 0), "Force different state bypassed lock");
        expect(machine.previous_state() == (transition ? 0 : -1), "Guard changed PreviousState");
    }
}

void transition_assigns_fields_before_end_begin_factory() {
    StateMachine machine;
    std::vector<std::string> events;
    auto observe = [&](const char* event) {
        expect(machine.state() == 1 && machine.previous_state() == 0 && machine.changed_states, "Callback observed stale state fields");
        events.push_back(event);
    };
    machine.set_callbacks(0, {{}, {}, {}, [&] { observe("end"); }});
    machine.set_callbacks(1, {{}, [&] { observe("factory"); return sequence({}); }, [&] { observe("begin"); }, {}});
    machine.set_state(0);
    machine.set_state(1);
    expect(events == std::vector<std::string>{"end", "begin", "factory"}, "Transition callback order");
    expect(machine.coroutine().active, "Factory iterator not installed");
}

void end_reentry_uses_current_begin_and_factory() {
    StateMachine machine;
    std::vector<std::string> events;
    machine.set_callbacks(0, {{}, {}, {}, [&] { events.push_back("end0"); machine.set_state(2); }});
    machine.set_callbacks(1, {{}, {}, [&] { events.push_back("begin1"); }, [&] { events.push_back("end1"); }});
    machine.set_callbacks(2, {{}, [&] { events.push_back("factory2"); return sequence({}); }, [&] { events.push_back("begin2"); }, {}});
    machine.set_state(0);
    machine.set_state(1);
    expect(events == std::vector<std::string>{"end0", "end1", "begin2", "factory2", "begin2", "factory2"}, "End reentry cached target");
    expect(machine.state() == 2 && machine.previous_state() == 1, "End reentry PreviousState overwritten");
}

void begin_reentry_uses_current_factory() {
    StateMachine machine;
    std::vector<int> factories;
    machine.set_callbacks(0, {{}, [&] { factories.push_back(0); return sequence({}); }, [&] { machine.set_state(1); }, {}});
    machine.set_callbacks(1, {{}, [&] { factories.push_back(1); return sequence({}); }, {}, {}});
    machine.set_state(0);
    expect(factories == std::vector<int>{1, 1}, "Begin reentry cached factory");
    expect(machine.previous_state() == 0 && machine.state() == 1, "Begin reentry state fields");
}

void factory_reentry_outer_result_replaces_inner_iterator() {
    StateMachine machine;
    auto outer = sequence({3.0f});
    machine.set_callbacks(0, {{}, [&] { machine.set_state(1); return outer; }, {}, {}});
    machine.set_callbacks(1, {{}, [] { return sequence({7.0f}); }, {}, {}});
    machine.set_state(0);
    machine.update(1, 1);
    expect(machine.state() == 1 && bits(machine.coroutine().wait_timer()) == bits(3.0f), "Factory reentry lost outer return ordering");
}

void update_transitions_then_runs_new_coroutine_same_tick() {
    StateMachine machine;
    std::vector<int> events;
    machine.set_callbacks(0, {[&] { events.push_back(0); return 1; }, [] { return sequence({99.0f}); }, {}, {}});
    machine.set_callbacks(1, {{}, [&] { return std::make_shared<Iterator>([&]() -> IteratorStep { events.push_back(1); return Yield{0.5f}; }); }, {}, {}});
    machine.set_state(0);
    machine.update(0.1f, 0.2f);
    expect(events == std::vector<int>{0, 1} && machine.changed_states && machine.previous_state() == 0, "Update/coroutine transition order");
    expect(bits(machine.coroutine().wait_timer()) == bits(0.5f), "New coroutine was not stepped");
}

void update_callback_reentry_then_returned_state() {
    StateMachine machine;
    machine.set_callbacks(0, {[&] { machine.set_state(1); return 2; }, {}, {}, {}});
    machine.set_state(0);
    machine.update(1, 1);
    expect(machine.state() == 2 && machine.previous_state() == 1, "Update return not assigned after callback reentry");
}

void mutable_update_capture_persists_between_updates() {
    StateMachine machine;
    machine.set_callbacks(0, {[calls = 0]() mutable { return ++calls == 2 ? 1 : 0; }, {}, {}, {}});
    machine.set_state(0);
    machine.update(1, 1);
    expect(machine.state() == 0, "Update transitioned before its second invocation");
    machine.update(1, 1);
    expect(machine.state() == 1, "Mutable update capture was reset between invocations");
}

void mutable_begin_capture_persists_between_transitions() {
    StateMachine machine;
    std::vector<int> calls;
    machine.set_callbacks(0, {{}, {}, [&, count = 0]() mutable { calls.push_back(++count); }, {}});
    machine.set_state(0);
    machine.force_state(0);
    expect(calls == std::vector<int>{1, 2}, "Mutable begin capture was reset between invocations");
}

void mutable_end_capture_persists_between_transitions() {
    StateMachine machine;
    std::vector<int> calls;
    machine.set_callbacks(0, {{}, {}, {}, [&, count = 0]() mutable { calls.push_back(++count); }});
    machine.set_state(0);
    machine.force_state(0);
    machine.set_state(1);
    expect(calls == std::vector<int>{1, 2}, "Mutable end capture was reset between invocations");
}

void mutable_factory_capture_persists_between_transitions() {
    StateMachine machine;
    machine.set_callbacks(0, {{}, [count = 0]() mutable { return sequence({static_cast<float>(++count)}); }, {}, {}});
    machine.set_state(0);
    machine.update(1, 1);
    expect(bits(machine.coroutine().wait_timer()) == bits(1.0f), "First factory result");
    machine.force_state(0);
    machine.update(1, 1);
    expect(bits(machine.coroutine().wait_timer()) == bits(2.0f), "Mutable factory capture was reset between invocations");
}

void coroutine_state_change_ignores_stale_yield() {
    StateMachine machine;
    machine.set_callbacks(0, {{}, [&] { return std::make_shared<Iterator>([&]() -> IteratorStep { machine.set_state(1); return Yield{99.0f}; }); }, {}, {}});
    machine.set_callbacks(1, {{}, [] { return sequence({0.5f}); }, {}, {}});
    machine.set_state(0);
    machine.update(1, 1);
    expect(machine.state() == 1 && machine.changed_states && bits(machine.coroutine().wait_timer()) == 0, "Coroutine transition applied stale yield");
    machine.update(1, 1);
    expect(!machine.changed_states && machine.previous_state() == 0 && bits(machine.coroutine().wait_timer()) == bits(0.5f), "ChangedStates reset or replacement resume");
}

void callback_replacement_keeps_executing_callback_alive() {
    StateMachine machine;
    bool destroyed = false;
    auto token = std::shared_ptr<int>(new int, [&](int* pointer) { destroyed = true; delete pointer; });
    machine.set_callbacks(0, {{}, {}, [&, token] { machine.set_callbacks(0, {}); expect(!destroyed, "Executing callback destroyed"); }, {}});
    token.reset();
    machine.set_state(0);
    expect(destroyed, "Callback leaked");
}

void installed_callback_self_replacement_is_owned_parameterized() {
    for (int phase : {0, 1, 2, 3}) {
        StateMachine machine;
        bool destroyed = false;
        auto token = std::shared_ptr<int>(new int, [&](int* pointer) { destroyed = true; delete pointer; });
        std::function<void()> replace = [&, token] {
            machine.set_callbacks(0, {});
            expect(!destroyed, "Self-replacement destroyed the executing callable");
        };
        StateCallbacks callbacks;
        if (phase == 0) callbacks.update = [replace] { replace(); return 0; };
        if (phase == 1) callbacks.begin = replace;
        if (phase == 2) callbacks.end = replace;
        if (phase == 3) callbacks.coroutine = [replace] { replace(); return sequence({}); };
        machine.set_callbacks(0, std::move(callbacks));
        callbacks = {};
        replace = {};
        token.reset();
        machine.set_state(0);
        if (phase == 0) machine.update(1, 1);
        if (phase == 2) machine.force_state(0);
        expect(destroyed, "Replaced callable leaked after invocation");
    }
}

void transition_refreshes_replaced_table_between_phases_parameterized() {
    for (bool replace_in_begin : {false, true}) {
        StateMachine machine;
        std::vector<int> begins;
        auto replace = [&] {
            machine.set_callbacks(1, {{}, [] { return sequence({2.0f}); }, [&] { begins.push_back(2); }, {}});
        };
        machine.set_callbacks(0, {{}, {}, {}, [&, replace_in_begin] { if (!replace_in_begin) replace(); }});
        machine.set_callbacks(1, {{}, [] { return sequence({1.0f}); }, [&, replace_in_begin] {
            begins.push_back(1);
            if (replace_in_begin) replace();
        }, {}});
        machine.set_state(0);
        machine.set_state(1);
        machine.update(1, 1);
        expect(begins == std::vector<int>{replace_in_begin ? 1 : 2}, "Transition cached the previous callback table");
        expect(bits(machine.coroutine().wait_timer()) == bits(2.0f), "Factory lookup used the replaced callback table");
    }
}

void transition_exception_preserves_ordered_state_parameterized() {
    for (int phase : {0, 1, 2}) {
        StateMachine machine;
        auto fail = [] { throw std::runtime_error("Synthetic callback failure"); };
        machine.set_callbacks(0, {{}, {}, {}, phase == 0 ? std::function<void()>{fail} : std::function<void()>{}});
        machine.set_callbacks(1, {{}, [&, phase] { if (phase == 2) fail(); return sequence({}); }, phase == 1 ? std::function<void()>{fail} : std::function<void()>{}, {}});
        machine.set_state(0);
        expect_throws<std::runtime_error>([&] { machine.set_state(1); });
        expect(machine.state() == 1 && machine.previous_state() == 0 && machine.changed_states, "Exception rolled back assigned state");
        expect(machine.coroutine().finished(), "Exception unexpectedly replaced previous coroutine");
    }
}

void step_exception_propagates_and_next_update_is_possible() {
    int calls = 0;
    Coroutine coroutine(std::make_shared<Iterator>([&]() -> IteratorStep { if (++calls == 1) throw std::runtime_error("Step failure"); return std::nullopt; }));
    expect_throws<std::runtime_error>([&] { coroutine.update(1, 1); });
    coroutine.update(1, 1);
    expect(calls == 2 && coroutine.finished(), "Exception left update permanently guarded");
}

void unsupported_inputs_fail_parameterized() {
    for (int invalid : {0, 1, 2, 3, 4, 5}) {
        StateMachine machine;
        Coroutine coroutine(false);
        expect_throws<std::invalid_argument>([&] {
            if (invalid == 0) { StateMachine bad(0); }
            if (invalid == 1) { StateMachine bad(-1); }
            if (invalid == 2) coroutine.replace(nullptr);
            if (invalid == 3) { Iterator bad({}); }
            if (invalid == 4) { coroutine.replace(sequence({std::numeric_limits<float>::infinity()})); coroutine.update(1, 1); }
            if (invalid == 5) coroutine.update(std::numeric_limits<float>::quiet_NaN(), 1);
        });
    }
}

void invalid_state_fails_before_mutation() {
    StateMachine machine;
    expect_throws<std::out_of_range>([&] { machine.set_state(10); });
    expect(machine.state() == -1 && !machine.changed_states, "Invalid state mutated fields");
}

void recursive_coroutine_update_fails_explicitly() {
    Coroutine coroutine(false);
    coroutine.replace(std::make_shared<Iterator>([&]() -> IteratorStep { coroutine.update(1, 1); return std::nullopt; }));
    expect_throws<std::logic_error>([&] { coroutine.update(1, 1); });
}

}

int main() {
    struct Test { const char* name; void (*run)(); };
    const Test tests[] = {
        {"null_yield_consumes_one_update", null_yield_consumes_one_update},
        {"wait_crossing_zero_never_resumes_parameterized", wait_crossing_zero_never_resumes_parameterized},
        {"zero_negative_integer_waits_parameterized", zero_negative_integer_waits_parameterized},
        {"child_push_pop_do_not_step_parent", child_push_pop_do_not_step_parent},
        {"cancel_and_replace_reset_parameterized", cancel_and_replace_reset_parameterized},
        {"mid_step_replacement_keeps_iterator_alive_parameterized", mid_step_replacement_keeps_iterator_alive_parameterized},
        {"direct_update_ignores_active_flag", direct_update_ignores_active_flag},
        {"completion_removal_parameterized", completion_removal_parameterized},
        {"attachment_initialization_parameterized", attachment_initialization_parameterized},
        {"locked_initialization_can_retry", locked_initialization_can_retry},
        {"force_and_lock_guards_parameterized", force_and_lock_guards_parameterized},
        {"transition_assigns_fields_before_end_begin_factory", transition_assigns_fields_before_end_begin_factory},
        {"end_reentry_uses_current_begin_and_factory", end_reentry_uses_current_begin_and_factory},
        {"begin_reentry_uses_current_factory", begin_reentry_uses_current_factory},
        {"factory_reentry_outer_result_replaces_inner_iterator", factory_reentry_outer_result_replaces_inner_iterator},
        {"update_transitions_then_runs_new_coroutine_same_tick", update_transitions_then_runs_new_coroutine_same_tick},
        {"update_callback_reentry_then_returned_state", update_callback_reentry_then_returned_state},
        {"mutable_update_capture_persists_between_updates", mutable_update_capture_persists_between_updates},
        {"mutable_begin_capture_persists_between_transitions", mutable_begin_capture_persists_between_transitions},
        {"mutable_end_capture_persists_between_transitions", mutable_end_capture_persists_between_transitions},
        {"mutable_factory_capture_persists_between_transitions", mutable_factory_capture_persists_between_transitions},
        {"coroutine_state_change_ignores_stale_yield", coroutine_state_change_ignores_stale_yield},
        {"callback_replacement_keeps_executing_callback_alive", callback_replacement_keeps_executing_callback_alive},
        {"installed_callback_self_replacement_is_owned_parameterized", installed_callback_self_replacement_is_owned_parameterized},
        {"transition_refreshes_replaced_table_between_phases_parameterized", transition_refreshes_replaced_table_between_phases_parameterized},
        {"transition_exception_preserves_ordered_state_parameterized", transition_exception_preserves_ordered_state_parameterized},
        {"step_exception_propagates_and_next_update_is_possible", step_exception_propagates_and_next_update_is_possible},
        {"unsupported_inputs_fail_parameterized", unsupported_inputs_fail_parameterized},
        {"invalid_state_fails_before_mutation", invalid_state_fails_before_mutation},
        {"recursive_coroutine_update_fails_explicitly", recursive_coroutine_update_fails_explicitly},
    };
    int failures = 0;
    for (const auto& test : tests) {
        try { test.run(); std::cout << "PASS " << test.name << '\n'; }
        catch (const std::exception& error) { ++failures; std::cerr << "FAIL " << test.name << ": " << error.what() << '\n'; }
    }
    return failures == 0 ? 0 : 1;
}
