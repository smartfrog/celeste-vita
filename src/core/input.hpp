#pragma once

namespace celeste {

struct ButtonSample {
    bool held = false;
    bool pressed = false;
    bool released = false;
    bool disabled = false;
    bool debug_override_pressed = false;
};

class VirtualButton final {
public:
    explicit VirtualButton(float buffer_time = 0.0f);

    ButtonSample sample;
    float buffer_time;

    bool check() const;
    bool pressed() const;
    bool released() const;
    bool repeating() const { return repeating_; }
    bool consumed() const { return consumed_; }
    bool can_repeat() const { return can_repeat_; }
    float buffer_counter() const { return buffer_counter_; }
    float repeat_counter() const { return repeat_counter_; }
    float first_repeat_time() const { return first_repeat_time_; }
    float multi_repeat_time() const { return multi_repeat_time_; }

    void update(float scaled_delta_time);
    void set_repeat(float repeat_time);
    void set_repeat(float first_repeat_time, float multi_repeat_time);
    void consume_buffer();
    void consume_press();

private:
    float first_repeat_time_ = 0.0f;
    float multi_repeat_time_ = 0.0f;
    float buffer_counter_ = 0.0f;
    float repeat_counter_ = 0.0f;
    bool can_repeat_ = false;
    bool consumed_ = false;
    bool repeating_ = false;
};

}
