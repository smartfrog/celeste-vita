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

inline Session make_session(const PlayerWorld& world,const PlayerFrameBank* bank,const RoomCatalog* catalog=nullptr,
                            const std::vector<draw_order::AuthoredDecalOwners>* visual_catalog=nullptr) {
    if constexpr(automatic_session_profile) {
        if(!bank) throw std::invalid_argument("Automatic session requires the animated Player bank");
        return Session(world,*bank,false,0,catalog,visual_catalog);
    } else {
        if(catalog || visual_catalog) throw std::invalid_argument("Room catalogs and visual metadata require the automatic session profile");
        return Session(world,{19,144},bank,0);
    }
}

}
