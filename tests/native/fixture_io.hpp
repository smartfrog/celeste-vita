#pragma once

#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace native_test {

inline float parse_float(const std::string& text) {
    if (text.at(0) == '@') {
        const auto value = static_cast<std::uint32_t>(std::stoul(text.substr(1), nullptr, 16));
        float result;
        std::memcpy(&result, &value, sizeof(result));
        return result;
    }
    std::size_t consumed;
    const float value = std::stof(text, &consumed);
    if (consumed != text.size()) throw std::invalid_argument("Invalid float: " + text);
    return value;
}

inline std::string bits(float value) {
    std::uint32_t raw;
    std::memcpy(&raw, &value, sizeof(raw));
    std::ostringstream output;
    output << std::hex << std::setfill('0') << std::setw(8) << raw;
    return output.str();
}

template<typename Runner>
int run_fixture(int argc, char** argv) {
    try {
        if (argc != 2) throw std::invalid_argument("Expected fixture path");
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("Cannot open fixture file");
        Runner runner;
        std::string line;
        std::size_t line_number = 0;
        while (std::getline(input, line)) {
            ++line_number;
            std::istringstream tokens(line);
            std::vector<std::string> fields;
            std::string token;
            while (tokens >> token) {
                if (token == "=>") break;
                fields.push_back(token);
            }
            if (fields.empty() || fields.front().at(0) == '#') continue;
            try { runner.run(fields); }
            catch (const std::exception& error) {
                throw std::runtime_error("Fixture line " + std::to_string(line_number) + ": " + error.what());
            }
        }
        if (input.bad()) throw std::runtime_error("Error reading fixture file");
        if (!std::cout) throw std::runtime_error("Error writing trace");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}

}
