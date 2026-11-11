#pragma once
#include <atomic>
#include <cstdint>
#include <limits>
#include <stdexcept>

namespace celeste {
inline std::uint64_t next_object_identity() {
    static std::atomic<std::uint32_t> next{0};
    auto value=next.load(std::memory_order_relaxed);
    do {
        if(value==std::numeric_limits<std::uint32_t>::max()) throw std::overflow_error("Object lifetime identity exhausted");
    } while(!next.compare_exchange_weak(value,value+1,std::memory_order_relaxed));
    return std::uint64_t(value)+1;
}
}
