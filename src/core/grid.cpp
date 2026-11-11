#include "movement.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace celeste {

TileGrid::TileGrid(std::int32_t columns, std::int32_t rows, std::vector<std::uint8_t> cells,
                   float cell_width, float cell_height, Vec2 offset)
    : columns_(columns), rows_(rows), cells_(std::move(cells)),
      cell_width_(cell_width), cell_height_(cell_height), offset_(offset) {
    if (columns < 0 || rows < 0 || static_cast<std::uint64_t>(columns) * static_cast<std::uint64_t>(rows) != cells_.size())
        throw std::invalid_argument("Grid dimensions must match its cell data");
    if (!std::isfinite(cell_width) || !std::isfinite(cell_height) || cell_width <= 0.0f || cell_height <= 0.0f ||
        !std::isfinite(offset.x) || !std::isfinite(offset.y) || !std::isfinite(width()) || !std::isfinite(height()))
        throw std::invalid_argument("Grid sizes must be positive and finite; dimensions and offsets finite");
    if (std::any_of(cells_.begin(), cells_.end(), [](auto cell) { return cell > 1; }))
        throw std::invalid_argument("Grid cells must be zero or one");
}

bool TileGrid::at(std::int32_t x, std::int32_t y) const {
    if (x < 0 || y < 0 || x >= columns_ || y >= rows_) return false;
    return cells_[static_cast<std::size_t>(y) * static_cast<std::size_t>(columns_) + static_cast<std::size_t>(x)] != 0;
}

}
