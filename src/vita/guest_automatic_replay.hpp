#pragma once

#include "diagnostic.hpp"
#include <array>
#include <stdexcept>

namespace celeste::diagnostic {

inline constexpr const char* guest_automatic_id="first_room_auto_death_v2";
inline constexpr const char* guest_automatic_source_sha256="b2123d17ef324e44535f20f75963ea9a177ea38217c8255162a2c97c45c04260";
inline constexpr unsigned guest_automatic_samples=365;
inline constexpr unsigned guest_automatic_exit_frame=364;

namespace automatic_fixture {
struct Event { unsigned frame; Controls controls; };
inline constexpr Controls right{false,true};
inline constexpr Controls right_cross{false,true,false,false,true};
inline constexpr Controls cross{false,false,false,false,true};
inline constexpr Controls start{false,false,false,false,false,false,true};
inline constexpr std::array<Event,14> events{{
    {0,{}},{36,right_cross},{37,right},{64,{}},{68,cross},{199,{}},{200,right_cross},
    {201,right},{228,{}},{232,cross},{235,{}},{362,cross},{363,right_cross},{364,start}
}};
constexpr bool valid() {
    for(unsigned i=0;i<events.size();++i) {
        const auto& event=events[i];
        const auto& input=event.controls;
        if((i && event.frame<=events[i-1].frame) || input.up || input.down || input.triangle || input.square || input.l ||
           (input.start && event.frame!=guest_automatic_exit_frame)) return false;
    }
    return events.back().frame==guest_automatic_exit_frame && events.back().controls.start &&
        guest_automatic_exit_frame+1==guest_automatic_samples;
}
static_assert(valid(),"Automatic fixture must contain only bounded raw input and terminal Start");
}

class GuestAutomaticReplay final {
public:
    Controls next(unsigned frame) {
        if(frame!=next_frame_ || frame>=guest_automatic_samples)
            throw std::invalid_argument("Guest automatic tick out of order or beyond bound");
        Controls controls;
        for(const auto& event:automatic_fixture::events) {
            if(event.frame>frame) break;
            controls=event.controls;
        }
        ++next_frame_;
        return controls;
    }
private:
    unsigned next_frame_=0;
};

}
