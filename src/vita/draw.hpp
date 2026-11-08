#pragma once
#include "assets.hpp"

namespace celeste::diagnostic {
void initialize_graphics();
void draw(const Room& room, const Player& player);
void finish_graphics();
}
