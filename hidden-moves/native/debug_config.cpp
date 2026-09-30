#include "debug_config.hpp"
#include <nn/result.h>
#include <nn/fs.h>

namespace debug_mount {
namespace {
void message(const char* s) { svcOutputDebugString(s, std::strlen(s)); }
}
void update(float delta) {
    if (std::isfinite(delta) && delta > 0) state.elapsed += delta;
    if (state.elapsed < 0.5f) return;
    state.elapsed = 0;
    if (!state.mounted) {
        state.mounted = nn::fs::MountSdCardForDebug("hmsd").isSuccess();
        if (!state.mounted) {
            if (!state.reported_mount_failure) message("HiddenMoves: debug SD mount unavailable; party mode retained\n");
            state.reported_mount_failure = true;
            return;
        }
    }
    nn::fs::FileHandle handle{};
    if (!nn::fs::OpenFile(&handle, "hmsd:/hidden-moves-debug.cfg", nn::fs::OpenMode_Read).isSuccess()) {
        // A removed file disables overrides. Invalid existing contents keep the
        // last valid configuration, so an editor's partial write is harmless.
        if (state.had_file) {
            state.config = {}; ++state.revision;
            state.had_file = false; state.last_hash = 0;
            message("HiddenMoves: debug file removed; party mode restored\n");
        }
        return;
    }
    char buffer[1025]{};
    long size = 0;
    bool valid = nn::fs::GetFileSize(&size, handle).isSuccess() && size > 0 && size <= 1024;
    if (valid) valid = nn::fs::ReadFile(handle, 0, buffer, static_cast<unsigned long>(size)).isSuccess();
    nn::fs::CloseFile(handle);
    if (!valid) return;
    state.had_file = true;
    uint64_t hash = 14695981039346656037ULL;
    for (long i = 0; i < size; ++i) { hash ^= static_cast<unsigned char>(buffer[i]); hash *= 1099511628211ULL; }
    if (hash == state.last_hash) return;
    state.last_hash = hash;
    Config config;
    if (std::memchr(buffer, 0, size) || !parse(buffer, config)) {
        message("HiddenMoves: invalid debug config ignored\n");
        return;
    }
    state.config = config; ++state.revision;
    message(config.enabled ? "HiddenMoves: live debug config applied\n" : "HiddenMoves: debug disabled; party mode restored\n");
}
}
