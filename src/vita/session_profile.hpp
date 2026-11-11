#pragma once

#include "diagnostic.hpp"
#include <stdexcept>

#if defined(CELESTE_ROOM_GUEST_AUTOMATIC) && defined(CELESTE_ROOM_GUEST_REPLAY)
#error "Guest automatic and legacy replay modes are exclusive"
#endif
#if defined(CELESTE_ROOM_GUEST_AUTOMATIC) && !defined(CELESTE_ROOM_ANIMATED_PLAYER)
#error "Guest automatic requires the animated Player"
#endif
#if defined(CELESTE_ROOM_DASH_PROBE) && (defined(CELESTE_ROOM_GUEST_AUTOMATIC) || defined(CELESTE_ROOM_GUEST_REPLAY))
#error "Dash probe and other guest modes are exclusive"
#endif
#if defined(CELESTE_ROOM_DASH_PROBE) && !defined(CELESTE_ROOM_ANIMATED_PLAYER)
#error "Dash probe requires the animated Player"
#endif

namespace celeste::diagnostic {

#if defined(CELESTE_ROOM_ANIMATED_PLAYER) && !defined(CELESTE_ROOM_GUEST_REPLAY)
inline constexpr bool automatic_session_profile=true;
#else
inline constexpr bool automatic_session_profile=false;
#endif

inline Session make_session(const PlayerWorld& world,const PlayerFrameBank* bank) {
    if constexpr(automatic_session_profile) {
        if(!bank) throw std::invalid_argument("Automatic session requires the animated Player bank");
        return Session(world,*bank);
    } else return Session(world,{19,144},bank,0);
}

}
