#pragma once
#include "assets.hpp"

namespace celeste::diagnostic {
void initialize_graphics();
std::string draw(const Room& room, const Player& player, const char* export_path = nullptr);
void finish_graphics();
}
