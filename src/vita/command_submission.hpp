#pragma once
#include "command_preflight.hpp"
#include "diagnostic.hpp"
#include <functional>

namespace celeste::command_submission {

struct UploadedPage {
    int id=0,width=0,height=0;
    unsigned texture=0;
};

struct View {
    Vec2 camera{};
    int width=960,height=544;
};

struct Projection {
    diagnostic::Viewport viewport;
    float left,right,top,bottom;
};

struct Sink {
    std::function<void(const Projection&)> begin;
    std::function<void(unsigned,const command_preflight::ReadyCommand&)> quad;
    std::function<void()> end;
    // Semantic zero-area Banner commands are acknowledged in global order and never
    // bind, color, draw or change batch state. Required only when such a command exists.
    std::function<void(const command_preflight::ReadyCommand&)> non_raster_ack;
};

// Exact page-ID set, including unused table pages. Caller owns verified pixel uploads,
// allocation capacity, handle lifetime and context; nonzero handles prove none of these.
// All input validation precedes callbacks. Empty valid frames emit no callbacks.
// Quad callbacks are limited to raster coverage; an all-semantic frame emits ordered
// acks without begin/end. Sink/driver failures propagate after start; submission is
// not rollback-atomic.
void submit(const command_preflight::ReadyFrame& frame,const std::vector<UploadedPage>& pages,
            const View& view,const Sink& sink);

}
