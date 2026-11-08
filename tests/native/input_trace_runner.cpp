#include "input.hpp"
#include "fixture_io.hpp"

using namespace celeste;
using namespace native_test;

namespace {

class InputRunner {
public:
    void run(const std::vector<std::string>& fields) {
        const auto& operation = fields.at(0);
        if (operation == "case") {
            name_ = fields.at(1);
            step_ = 0;
            delta_ = 0.0f;
            button_ = VirtualButton(parse_float(fields.at(2)));
            return;
        }
        ++step_;
        if (operation == "tick") delta_ = parse_float(fields.at(1));
        trace("before", operation);
        if (operation == "sample") button_.sample = {flag(fields.at(1)), flag(fields.at(2)), flag(fields.at(3)), flag(fields.at(4)), flag(fields.at(5))};
        else if (operation == "tick") button_.update(delta_);
        else if (operation == "repeat") button_.set_repeat(parse_float(fields.at(1)));
        else if (operation == "repeat_pair") button_.set_repeat(parse_float(fields.at(1)), parse_float(fields.at(2)));
        else if (operation == "buffer") button_.buffer_time = parse_float(fields.at(1));
        else if (operation == "consume_buffer") button_.consume_buffer();
        else if (operation == "consume_press") button_.consume_press();
        else if (operation != "query") throw std::invalid_argument("Unknown input operation");
        trace("after", operation);
    }

private:
    VirtualButton button_;
    std::string name_;
    int step_ = 0;
    float delta_ = 0.0f;

    static bool flag(const std::string& value) {
        if (value != "0" && value != "1") throw std::invalid_argument("Invalid sample flag");
        return value == "1";
    }

    void trace(const std::string& phase, const std::string& operation) const {
        const auto& s = button_.sample;
        std::cout << name_ << '\t' << step_ << '\t' << phase << '\t' << operation
                  << '\t' << bits(button_.buffer_time) << '\t' << bits(button_.first_repeat_time())
                  << '\t' << bits(button_.multi_repeat_time()) << '\t' << bits(button_.buffer_counter())
                  << '\t' << bits(button_.repeat_counter()) << '\t' << button_.can_repeat()
                  << '\t' << button_.consumed() << '\t' << button_.repeating()
                  << '\t' << s.held << '\t' << s.pressed << '\t' << s.released << '\t' << s.disabled
                  << '\t' << s.debug_override_pressed << '\t' << button_.check() << '\t' << button_.pressed()
                  << '\t' << button_.released() << '\t' << bits(delta_) << '\n';
    }
};

}

int main(int argc, char** argv) { return run_fixture<InputRunner>(argc, argv); }
