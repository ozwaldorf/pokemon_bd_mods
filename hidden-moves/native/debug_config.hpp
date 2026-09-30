#pragma once
#include "placements.hpp"
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <initializer_list>

namespace debug_mount {
struct Config {
    bool enabled = false;
    char model[13] = "party";
    Placement placement{{0, 1, 0}, {0, 0, 0}, {1, 1, 1}};
};
struct State {
    Config config{};
    unsigned revision = 0;
    float elapsed = 1;
    bool mounted = false, reported_mount_failure = false;
    uint64_t last_hash = 0;
    bool had_file = false;
};
inline State state;

inline bool same_model(const Config& a, const Config& b) {
    const char* x = a.enabled ? a.model : "party";
    const char* y = b.enabled ? b.model : "party";
    return std::strcmp(x, y) == 0;
}
inline bool valid_model(const char* s) {
    if (std::strcmp(s, "party") == 0) return true;
    if (std::strlen(s) != 12 || s[0] != 'p' || s[1] != 'm' || s[6] != '_' || s[9] != '_') return false;
    for (int i : {2, 3, 4, 5, 7, 8, 10, 11}) if (s[i] < '0' || s[i] > '9') return false;
    int species = (s[2]-'0')*1000 + (s[3]-'0')*100 + (s[4]-'0')*10 + s[5]-'0';
    return species >= 1 && species <= 493;
}
inline char* trim(char* s) {
    while (*s == ' ' || *s == '\t' || *s == '\r') ++s;
    size_t n = std::strlen(s);
    while (n && (s[n-1] == ' ' || s[n-1] == '\t' || s[n-1] == '\r')) s[--n] = 0;
    return s;
}
inline bool vector(char* s, game::Vector3& output, bool scale) {
    float values[3];
    for (int i = 0; i < 3; ++i) {
        char* end;
        values[i] = std::strtof(s, &end);
        if (end == s || !std::isfinite(values[i])) return false;
        if (scale ? (values[i] < 0.01f || values[i] > 10) : std::abs(values[i]) > 1000) return false;
        end = trim(end);
        if (i < 2) { if (*end != ',') return false; s = end + 1; }
        else if (*end) return false;
    }
    output = {values[0], values[1], values[2]};
    return true;
}
// Parse into a temporary value: malformed/partial edits cannot affect the mount.
inline bool parse(char* text, Config& output) {
    Config value;
    unsigned seen = 0;
    for (char* line = text; line && *line;) {
        char* next = std::strchr(line, '\n');
        if (next) *next++ = 0;
        if (char* comment = std::strchr(line, '#')) *comment = 0;
        line = trim(line);
        if (*line) {
            char* split = std::strchr(line, '=');
            if (!split) return false;
            *split++ = 0;
            char* key = trim(line); char* arg = trim(split);
            unsigned bit = 0;
            if (std::strcmp(key, "enabled") == 0) {
                bit = 1;
                if (std::strcmp(arg, "0") && std::strcmp(arg, "1")) return false;
                value.enabled = *arg == '1';
            } else if (std::strcmp(key, "model") == 0) {
                bit = 2; if (!valid_model(arg)) return false;
                std::strcpy(value.model, arg);
            } else if (std::strcmp(key, "offset") == 0) {
                bit = 4; if (!vector(arg, value.placement.offset, false)) return false;
            } else if (std::strcmp(key, "rotation") == 0) {
                bit = 8; if (!vector(arg, value.placement.rotation, false)) return false;
            } else if (std::strcmp(key, "scale") == 0) {
                bit = 16; if (!vector(arg, value.placement.scale, true)) return false;
            } else return false;
            if (seen & bit) return false;
            seen |= bit;
        }
        line = next;
    }
    if (!(seen & 1) || (value.enabled && seen != 31)) return false;
    output = value;
    return true;
}
void update(float delta);
}
