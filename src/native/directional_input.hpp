#pragma once

namespace celeste {

// NATIVE VITA FIXTURE ASSUMPTION: standard analog bytes are centred at 128 and
// increase right/down. This is not an original-source or hardware calibration.
struct StickReading {
    unsigned lx = 128;
    unsigned ly = 128;
    bool valid = false;
};

struct StickVector {
    float x = 0.0f;
    float y = 0.0f;
};

StickVector normalize_vita_stick(const StickReading& reading);

struct DirectionalButtons {
    bool left = false, right = false, up = false, down = false;
};

struct DirectionalInput {
    int move_x = 0, move_y = 0, aim_x = 0, aim_y = 0;
};

struct AimDirection {
    int x = 0, y = 0;
};

AimDirection snap_aim_direction(const StickVector& aim);

class DirectionalResolver final {
public:
    DirectionalInput update(const DirectionalButtons& buttons, const StickVector& stick);

private:
    int move_x_ = 0, move_y_ = 0;
    bool move_x_turned_ = false, move_y_turned_ = false;
    float aim_x_ = 0.0f, aim_y_ = 0.0f;
    bool aim_x_turned_ = false, aim_y_turned_ = false;
};

}
