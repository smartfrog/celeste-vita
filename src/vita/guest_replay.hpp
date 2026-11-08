#pragma once

#include "diagnostic.hpp"
#include <array>
#include <stdexcept>

namespace celeste::diagnostic {

inline constexpr const char* guest_replay_id = "first_room_climb_dash_v1";
inline constexpr unsigned guest_replay_frames = 250;

namespace replay_fixture {
struct Event { unsigned frame; Controls controls; };
inline constexpr Controls left{true};
inline constexpr Controls left_cross{true,false,false,false,true};
inline constexpr Controls left_grab{true,false,false,false,false,false,false,false,true};
inline constexpr Controls grab{false,false,false,false,false,false,false,false,true};
inline constexpr Controls up_grab{false,false,true,false,false,false,false,false,true};
inline constexpr Controls reset{false,false,false,false,false,true};
inline constexpr Controls cross{false,false,false,false,true};
inline constexpr Controls up{false,false,true};
inline constexpr Controls up_square{false,false,true,false,false,false,false,true};
inline constexpr Controls right{false,true};
inline constexpr Controls start{false,false,false,false,false,false,true};
inline constexpr std::array<Event,21> events{{
    {118,left},{120,left_cross},{124,left},{132,left_grab},{134,grab},{136,up_grab},
    {144,grab},{148,{}},{162,reset},{164,{}},{166,cross},{168,{}},{171,up},
    {173,up_square},{175,up},{190,{}},{192,right},{243,{}},{245,reset},{247,{}},{249,start}
}};
constexpr bool ordered() {
    for(unsigned i=1;i<events.size();++i) if(events[i-1].frame>=events[i].frame || events[i-1].controls.start) return false;
    return events.back().frame+1==guest_replay_frames && events.back().controls.start;
}
static_assert(ordered(),"Guest replay must be ordered, bounded, and end with Start");
}

class GuestReplay final {
public:
    Controls next(unsigned frame) {
        if(frame!=next_frame_ || frame>=guest_replay_frames) throw std::invalid_argument("Guest replay tick out of order or beyond bound");
        if(event_<replay_fixture::events.size() && frame==replay_fixture::events[event_].frame)
            current_=replay_fixture::events[event_++].controls;
        ++next_frame_;
        return current_;
    }
private:
    Controls current_{};
    unsigned event_=0,next_frame_=0;
};

}
