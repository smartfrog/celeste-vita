#pragma once
#include "lifecycle.hpp"

namespace native_test {
inline celeste::PlayerFrameBank lifecycle_bank() {
    celeste::PlayerFrameBank result;
    result.pages=1;
    result.frames.push_back({"fixture",0,1,1,8,8,0,0,32,32,{},0,true});
    result.frames.push_back({"characters/player/sweat/idle00",0,1,1,8,8,0,0,32,32,{},0,false});
    for(const char* id:{"idle","idleA","idleB","idleC","runSlow","runFast","runStumble","flip","skid","jumpSlow","jumpFast","fallSlow","fallFast","duck","edge","edgeBack","push","lookUp","climbUp","climbLookBackStart","climbLookBack","dangling","wallslide","dash"})
        result.animations.push_back({id,0.1f,id,{0}});
    for(const char* id:{"deadup","deaddown","deadside"}) result.animations.push_back({id,0.02f,"",{0}});
    return result;
}
struct LifecycleFixture {
    celeste::TileGrid grid{40,23,std::vector<std::uint8_t>(40*23,1)};
    celeste::Body floor{{0,144},std::nullopt,true,&grid};
    std::vector<celeste::StaticSpike> spikes{{{64,144},8,celeste::SpikeDirection::up},{{160,144},32,celeste::SpikeDirection::up},
        {{200,144},48,celeste::SpikeDirection::up},{{240,144},48,celeste::SpikeDirection::up},{{300,128},16,celeste::SpikeDirection::left}};
    celeste::PlayerWorld world;
    celeste::PlayerFrameBank frames=lifecycle_bank();
    LifecycleFixture() {
        world.bounds_left=0;world.bounds_right=320;
        world.collision.solids={&floor};world.safe_ground={&floor};
        for(const auto& spike:spikes) world.spikes.push_back(&spike);
    }
};
}
