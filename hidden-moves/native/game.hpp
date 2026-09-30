#pragma once

#include <cstddef>
#include <cstdint>
#include "exlaunch.hpp"

// Brilliant Diamond 1.3.0. Addresses are RVAs, not NSO file offsets.
namespace game {
using Object = void*;
struct Vector3 { float x, y, z; };
struct Handle { int32_t value; };

template <typename R, typename... A>
R call(uintptr_t rva, A... args) {
    return reinterpret_cast<R (*)(A...)>(exl::util::modules::GetTargetOffset(rva))(args...);
}
template <typename T>
T field(Object object, size_t offset) {
    return *reinterpret_cast<T*>(reinterpret_cast<uintptr_t>(object) + offset);
}
inline bool alive(Object obj) {
    return obj && call<bool>(0x268a7d0, obj, nullptr);
}
inline Object string(const char* value) {
    return call<Object>(0x26fb3e0, nullptr, value, nullptr);
}

// Native module globals are outside the managed GC's root set. Retain every
// managed object held across frames using normal GC handles (not raw pointers).
struct Root {
    Handle handle{};
    Object get() const {
        return handle.value ? call<Object>(0x22c62b0, handle.value, nullptr) : nullptr;
    }
    void clear() {
        if (handle.value) call<void>(0x22c6510, handle.value, nullptr);
        handle.value = 0;
    }
    void set(Object obj) {
        clear();
        if (obj) handle = call<Handle>(0x22c6410, obj, nullptr);
    }
};
struct ScopedRoot : Root {
    ~ScopedRoot() { clear(); }
};
inline bool string_equals(Object value, const char* ascii) {
    if (!value) return false;
    const int length = field<int>(value, 0x10);
    for (int i = 0; i < length; ++i) {
        if (!ascii[i] || field<uint16_t>(value, 0x14 + i * 2) != static_cast<unsigned char>(ascii[i])) return false;
    }
    return length >= 0 && !ascii[length];
}
inline void store_object(Object object, size_t offset, Object value) {
    auto* slot = reinterpret_cast<Object*>(reinterpret_cast<uintptr_t>(object) + offset);
    *slot = value;
    call<void>(0x2afa20, slot, value); // IL2CPP GC write barrier.
}

constexpr uintptr_t AppearSwim = 0x1db4000;
constexpr uintptr_t ChangeSwim = 0x1db2640;
constexpr uintptr_t PlayerLateUpdate = 0x1da3fd0;
constexpr uintptr_t CharacterDisable = 0x1788540;
constexpr uintptr_t RendererEnabled = 0x269a090;
constexpr size_t BibarelRenderer = 0x1d8;
constexpr size_t SurfTransform = 0x388;

inline Object first_user(int move) {
    Object party = call<Object>(0x2ce2b50, nullptr);
    if (!party) return nullptr;
    const auto count = call<uint32_t>(0x2056af0, party, nullptr);
    if (count > 6) return nullptr;
    for (uint32_t i = 0; i < count; ++i) {
        Object member = call<Object>(0x20556f0, party, i, nullptr);
        if (!member || call<bool>(0x204c9d0, member, nullptr)) continue;
        if (call<bool>(0x2049370, member, 2, nullptr)) continue;
        if (call<bool>(0x2045ea0, member, move, nullptr)) return member;
    }
    return nullptr;
}
inline Object field_bundle(Object pokemon) {
    const int id = call<int>(0x2ccd050, pokemon, nullptr);
    Object catalog = call<Object>(0x2cccf40, id, nullptr);
    return catalog ? call<Object>(0x186b360, field<Object>(catalog, 0x28), nullptr) : nullptr;
}
inline Object request_bundle(Object name) {
    Object request = call<Object>(0x22dbfb0, name, true, nullptr, nullptr, nullptr);
    call<Object>(0x22dc320, nullptr, nullptr);
    return request;
}
inline bool waiting(Object request) {
    return call<bool>(0x22e7d80, request, nullptr);
}
inline Object requested_prefab(Object request) {
    Object item = call<Object>(0x22e7b70, request, nullptr);
    if (!item) return nullptr;
    Object cache = field<Object>(item, 0x48);
    return cache ? call<Object>(0x22d6960, cache, nullptr) : nullptr;
}
inline void unload(Object name) {
    if (name) call<int>(0x22dbde0, name, nullptr);
}
inline Object component(Object obj, const char* name) {
    Object type = call<Object>(0x2b1e1d0, string(name), nullptr);
    return type ? call<Object>(0x26a8240, obj, type, nullptr) : nullptr;
}
inline Object children(Object obj, const char* name) {
    Object type = call<Object>(0x2b1e1d0, string(name), nullptr);
    return type ? call<Object>(0x26b1710, obj, type, true, nullptr) : nullptr;
}
inline size_t array_length(Object array) { return array ? field<size_t>(array, 0x18) : 0; }
inline Object array_item(Object array, size_t index) {
    return field<Object>(array, 0x20 + index * sizeof(Object));
}
inline void active(Object obj, bool enabled) {
    if (alive(obj)) call<void>(0x26b19c0, obj, enabled, nullptr);
}
inline void destroy(Object obj) {
    if (alive(obj)) call<void>(0x268b1f0, obj, nullptr);
}
}
