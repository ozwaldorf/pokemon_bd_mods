#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <string_view>

uintptr_t mock_address(uintptr_t);
void mock_original(const char*, void*, bool, void*);
void mock_original(const char*, void*, float, float, void*);
void mock_original(const char*, void*, float, void*);
void mock_original(const char*, void*, void*);
void mock_original(const char*, void*, int, void*);
bool mock_cut_in_original(void*, void*);
bool mock_waterfall_original(void*, void*);
bool mock_rock_climb_original(void*, void*);
bool mock_fly_departure_original(void*, void*);
bool mock_fly_arrival_original(void*, void*);
void mock_message_original(void*, void*, int, void*);
inline void svcOutputDebugString(const char*, size_t) {}
namespace exl::util::modules {
inline uintptr_t GetTargetOffset(uintptr_t rva) { return mock_address(rva); }
}
namespace exl::hook { inline void Initialize() {} }
template <size_t N> struct HookName {
    char value[N];
    constexpr HookName(const char (&text)[N]) {
        for (size_t i = 0; i < N; ++i) value[i] = text[i];
    }
};
template <HookName Name> struct TestHook {
    template <typename... Args> static auto Orig(Args... args) {
        if constexpr (std::string_view(Name.value) == "CutInCommand") return mock_cut_in_original(args...);
        else if constexpr (std::string_view(Name.value) == "WaterfallCommand") return mock_waterfall_original(args...);
        else if constexpr (std::string_view(Name.value) == "RockClimbCommand") return mock_rock_climb_original(args...);
        else if constexpr (std::string_view(Name.value) == "FlyDeparture") return mock_fly_departure_original(args...);
        else if constexpr (std::string_view(Name.value) == "FlyArrival") return mock_fly_arrival_original(args...);
        else if constexpr (std::string_view(Name.value) == "TraversalMessage") return mock_message_original(args...);
        else mock_original(Name.value, args...);
    }
    static void InstallAtOffset(uintptr_t) {}
};
#define HOOK_DEFINE_TRAMPOLINE(Name) struct Name : TestHook<HookName{#Name}>
#define EXL_ABORT(...) std::abort()
