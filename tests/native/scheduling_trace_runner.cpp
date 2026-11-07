#include "scheduling.hpp"
#include "fixture_io.hpp"

#include <map>

using namespace celeste;
using namespace native_test;

namespace {

class SyntheticFailure : public std::runtime_error {
public:
    SyntheticFailure() : std::runtime_error("Synthetic script failure") {}
};

std::vector<std::string> split(const std::string& text, char separator) {
    std::istringstream input(text);
    std::vector<std::string> fields;
    std::string field;
    while (std::getline(input, field, separator)) fields.push_back(field);
    return fields;
}

class SchedulingRunner {
public:
    void run(const std::vector<std::string>& fields) {
        const auto& operation = fields.at(0);
        if (operation == "case") {
            name_ = fields.at(1);
            step_ = 0;
            delta_ = raw_delta_ = 0.0f;
            scripts_.clear();
            machine_.reset();
            standalone_.reset();
            remove_ = fields.at(3) == "1";
            if (fields.at(2) == "C") standalone_ = std::make_unique<Coroutine>(remove_);
            else machine_ = std::make_unique<StateMachine>(std::stoi(fields.at(3)));
            return;
        }
        if (operation == "script") {
            if (!scripts_.emplace(fields.at(1), std::vector<std::string>(fields.begin() + 2, fields.end())).second)
                throw std::invalid_argument("Duplicate script");
            return;
        }
        if (operation == "callbacks") {
            const int index = std::stoi(fields.at(1));
            StateCallbacks callbacks;
            if (fields.at(2) != "-") callbacks.update = [this, index, spec = fields[2]] {
                trace("update", std::to_string(index));
                actions(spec);
                return std::stoi(split(split(spec, ',').back(), ':').at(1));
            };
            if (fields.at(3) != "-") callbacks.coroutine = [this, index, spec = fields[3]] {
                trace("factory", std::to_string(index));
                actions(spec);
                return script(split(split(spec, ',').back(), ':').at(1));
            };
            if (fields.at(4) != "-") callbacks.begin = [this, index, spec = fields[4]] { trace("begin", std::to_string(index)); actions(spec); };
            if (fields.at(5) != "-") callbacks.end = [this, index, spec = fields[5]] { trace("end", std::to_string(index)); actions(spec); };
            machine_->set_callbacks(index, std::move(callbacks));
            return;
        }
        ++step_;
        try {
            if (operation == "tick") {
                delta_ = parse_float(fields.at(1)); raw_delta_ = parse_float(fields.at(2));
                const auto removals = coroutine().removal_events();
                if (machine_) machine_->update(delta_, raw_delta_); else coroutine().update(delta_, raw_delta_);
                if (coroutine().removal_events() != removals) trace("remove", "-");
            } else if (operation == "construct") standalone_ = std::make_unique<Coroutine>(script(fields.at(1)), remove_);
            else if (operation == "replace") coroutine().replace(script(fields.at(1)));
            else if (operation == "cancel") coroutine().cancel();
            else if (operation == "raw") coroutine().use_raw_delta_time = fields.at(1) == "1";
            else if (operation == "active") coroutine().active = fields.at(1) == "1";
            else if (operation == "remove") coroutine().remove_on_complete = fields.at(1) == "1";
            else if (operation == "lock") machine_->locked = fields.at(1) == "1";
            else if (operation == "set") machine_->set_state(std::stoi(fields.at(1)));
            else if (operation == "force") machine_->force_state(std::stoi(fields.at(1)));
            else if (operation == "added") machine_->added(fields.at(1) == "1");
            else if (operation == "entity_added") machine_->entity_added();
            else if (operation != "snapshot") throw std::invalid_argument("Unknown scheduling operation");
            trace("return", operation);
        } catch (const SyntheticFailure&) { trace("throw", operation); }
    }

private:
    std::string name_;
    int step_ = 0;
    float delta_ = 0.0f, raw_delta_ = 0.0f;
    bool remove_ = true;
    std::unique_ptr<StateMachine> machine_;
    std::unique_ptr<Coroutine> standalone_;
    std::map<std::string, std::vector<std::string>> scripts_;

    Coroutine& coroutine() { return machine_ ? machine_->coroutine() : *standalone_; }

    void trace(const std::string& event, const std::string& detail) {
        const auto& c = coroutine();
        std::cout << name_ << '\t' << step_ << '\t' << event << '\t' << detail
                  << '\t' << (machine_ ? machine_->state() : -1) << '\t' << (machine_ ? machine_->previous_state() : -1)
                  << '\t' << (machine_ && machine_->changed_states) << '\t' << (machine_ && machine_->locked)
                  << '\t' << c.active << '\t' << c.finished() << '\t' << bits(c.wait_timer())
                  << '\t' << c.stack_depth() << '\t' << c.ended() << '\t' << c.removal_events()
                  << '\t' << c.use_raw_delta_time << '\t' << bits(delta_) << '\t' << bits(raw_delta_) << '\n';
    }

    void actions(const std::string& spec) {
        for (const auto& token : split(spec, ',')) {
            const auto fields = split(token, ':');
            const auto& kind = fields.at(0);
            if (kind == "set") machine_->set_state(std::stoi(fields.at(1)));
            else if (kind == "force") machine_->force_state(std::stoi(fields.at(1)));
            else if (kind == "lock") machine_->locked = fields.at(1) == "1";
            else if (kind == "cancel") coroutine().cancel();
            else if (kind == "replace") coroutine().replace(script(fields.at(1)));
            else if (kind == "throw") throw SyntheticFailure();
            else if (kind != "record" && kind != "return" && kind != "script") throw std::invalid_argument("Unknown callback action");
        }
    }

    IteratorPtr script(const std::string& identity) {
        const auto tokens = scripts_.at(identity);
        return std::make_shared<Iterator>([this, identity, tokens, index = std::size_t{0}]() mutable -> IteratorStep {
            trace("move", identity + ":" + std::to_string(index));
            if (index == tokens.size()) return std::nullopt;
            const auto fields = split(tokens[index++], ':');
            const auto& kind = fields.at(0);
            if (kind == "n") return Yield{std::monostate{}};
            if (kind == "done") return std::nullopt;
            if (kind == "throw") throw SyntheticFailure();
            if (kind == "i") return Yield{static_cast<std::int32_t>(std::stol(fields.at(1)))};
            if (kind == "f") return Yield{parse_float(fields.at(1))};
            if (kind == "child") return Yield{script(fields.at(1))};
            if (kind == "cancel") coroutine().cancel();
            else if (kind == "replace") coroutine().replace(script(fields.at(1)));
            else if (kind == "set") machine_->set_state(std::stoi(fields.at(1)));
            else throw std::invalid_argument("Unknown iterator token");
            if (fields.back() == "done") return std::nullopt;
            return Yield{std::monostate{}};
        });
    }
};

}

int main(int argc, char** argv) { return run_fixture<SchedulingRunner>(argc, argv); }
