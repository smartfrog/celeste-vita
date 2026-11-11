#pragma once

#include "guest_automatic_replay.hpp"
#include "guest_record.hpp"
#include <cstdio>
#include <string>

namespace celeste::diagnostic {

template<class... Args> std::string automatic_record(const char* format,Args... args) {
    return bounded_guest_record<512>("Guest automatic record exceeds bound",format,args...);
}

class GuestAutomaticObserver final {
public:
    explicit GuestAutomaticObserver(const Session& session) {
        if(!session.lifecycle()) throw std::invalid_argument("Guest automatic requires the production lifecycle Session");
        const auto& stats=session.lifecycle()->stats();
        valid_=session.player().state_machine().state()==14 && !session.player().death().dead && session.resets()==0 &&
            stats.reloads==0 && stats.room_deaths==0 && stats.save_deaths==0 && stats.jumps==0;
        previous_clock_=session.lifecycle()->context().clock.frame_counter;
    }
    std::string observe(unsigned frame,const Sample& sample,const Session& session) {
        if(frame!=samples_ || frame>=guest_automatic_samples) throw std::invalid_argument("Guest automatic observation out of order");
        if(!session.lifecycle()) throw std::invalid_argument("Guest automatic lost its lifecycle Session");
        const auto& stats=session.lifecycle()->stats();
        const auto state=session.player().state_machine().state();
        const auto dead=session.player().death().dead;
        const auto clock=session.lifecycle()->context().clock.frame_counter;
        valid_=valid_ && !sample.reset && session.resets()==0 && session.exiting()==sample.exit;
        if(!previous_dead_ && dead) {
            ++deaths_;
            valid_=valid_ && normal_entries_==deaths_ && stats.room_deaths==deaths_ && stats.save_deaths==deaths_;
        }
        if(stats.reloads!=reloads_) {
            valid_=valid_ && stats.reloads==reloads_+1 && deaths_==stats.reloads && state==14 && !dead;
            reloads_=stats.reloads;
        }
        if(previous_state_==14 && state==0 && !dead) {
            valid_=valid_ && normal_entries_==stats.reloads && deaths_==stats.reloads;
            ++normal_entries_;
        }
        if(sample.exit) valid_=valid_ && frame==guest_automatic_exit_frame && clock==previous_clock_;
        previous_state_=state;
        previous_dead_=dead;
        previous_clock_=clock;
        ++samples_;
        return automatic_record("guest_automatic fixture=%s frame=%u x=%d y=%d jump=%d reset=%d exit=%d state=%d dead=%d reloads=%u room_deaths=%u save_deaths=%u jumps=%u",
            guest_automatic_id,frame,sample.player.x,sample.player.y,int(sample.player.jump.held),int(sample.reset),int(sample.exit),
            state,int(dead),stats.reloads,stats.room_deaths,stats.save_deaths,stats.jumps);
    }
    bool complete(const Session& session) const {
        if(!session.lifecycle()) return false;
        const auto& stats=session.lifecycle()->stats();
        return valid_ && samples_==guest_automatic_samples && session.exiting() && session.resets()==0 &&
            !session.player().death().dead && session.player().state_machine().state()==0 &&
            normal_entries_==3 && deaths_==2 && stats.reloads==2 && stats.room_deaths==2 && stats.save_deaths==2 &&
            stats.jumps==3 && stats.respawn_callbacks==3 && stats.wipe_callbacks==2;
    }
    std::string completion_record(const Session& session) const {
        if(!session.lifecycle()) throw std::invalid_argument("Guest automatic completion requires its lifecycle Session");
        const auto& stats=session.lifecycle()->stats();
        return automatic_record("guest_automatic_complete fixture=%s samples=%u exit_frame=%u reloads=%u room_deaths=%u save_deaths=%u jumps=%u full_completion=%d",
            guest_automatic_id,samples_,guest_automatic_exit_frame,stats.reloads,stats.room_deaths,stats.save_deaths,stats.jumps,int(complete(session)));
    }
    unsigned samples() const { return samples_; }
private:
    unsigned samples_=0,normal_entries_=0,deaths_=0,reloads_=0;
    std::uint64_t previous_clock_=0;
    int previous_state_=14;
    bool previous_dead_=false,valid_=false;
};

}
