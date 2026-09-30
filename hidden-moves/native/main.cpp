#include "game.hpp"
#include "signatures.hpp"
#include "placements.hpp"
#include "debug_config.hpp"
#include <cstdio>

namespace {
using namespace game;

enum class Phase { Empty, Loading, Ready, Failed, Retiring };
struct Session {
    Root owner, renderer, bundle, request, model, animation, member;
    Phase phase = Phase::Empty;
    bool visible = false;
    bool boarding = false;
    int species = 0;
    debug_mount::Config debug;
} session;
unsigned debug_revision = 0;
int traversal_move = 57;

void log(const char* message) {
    size_t size = 0;
    while (message[size]) ++size;
    svcOutputDebugString(message, size);
}

void set_original_visibility(Object renderer, bool visible);
void update_visibility();
void trace_climb_model() {
    if (traversal_move != 431 || session.phase != Phase::Ready || !alive(session.model.get())) return;
    Object model = session.model.get();
    Object transform = call<Object>(0x26b18d0, model, nullptr);
    const Vector3 position = call<Vector3>(0x299d1c0, transform, nullptr);
    const Vector3 scale = call<Vector3>(0x299f5c0, transform, nullptr);
    char message[256];
    std::snprintf(message, sizeof(message),
        "HiddenMoves: Rock Climb model species=%d visible=%d hierarchy=%d world=(%.2f,%.2f,%.2f) scale=(%.2f,%.2f,%.2f)\n",
        session.species, session.visible, call<bool>(0x26b1a60, model, nullptr),
        position.x, position.y, position.z, scale.x, scale.y, scale.z);
    log(message);
}

void apply_placement() {
    Object model = session.model.get();
    if (!alive(model)) return;
    Object transform = call<Object>(0x26b18d0, model, nullptr);
    const auto placement = session.debug.enabled ? session.debug.placement : placement_for(session.species, traversal_move);
    call<void>(0x299d3d0, transform, placement.offset, nullptr);
    call<void>(0x299d770, transform, placement.rotation, nullptr);
    call<void>(0x299e000, transform, placement.scale, nullptr);
}

void finish_request() {
    session.request.clear();
    unload(session.bundle.get());
    session.bundle.clear();
    session.phase = Phase::Empty;
}

void stop() {
    // Save the desired vanilla visibility, not the false value we imposed.
    Object renderer = session.renderer.get();
    if (session.animation.get()) call<void>(0x211e7b0, session.animation.get(), nullptr);
    session.animation.clear();
    destroy(session.model.get());
    session.model.clear();
    if (alive(renderer)) set_original_visibility(renderer, session.visible);
    session.renderer.clear();
    session.owner.clear();
    session.member.clear();
    if (session.request.get() && waiting(session.request.get())) {
        // The sequencer owns a live request: don't unload its bundle mid-load.
        session.phase = Phase::Retiring;
    } else {
        finish_request();
    }
}

void begin(Object player) {
    if (session.phase != Phase::Empty || !alive(player)) return;
    session.owner.set(player);
    session.boarding = traversal_move != 57 || !call<bool>(0x1dac820, player, nullptr);
    session.phase = Phase::Failed; // At most one attempt per traversal session.
    session.debug = debug_mount::state.config;
    const bool override_model = session.debug.enabled && std::strcmp(session.debug.model, "party") != 0;
    Object member = override_model ? nullptr : first_user(traversal_move);
    if (!override_model && !member) {
        log("HiddenMoves: no eligible traversal user; keeping Bibarel\n");
        return;
    }
    session.member.set(member);
    Object renderer = field<Object>(player, BibarelRenderer);
    if (!alive(renderer)) return;
    Object bundle = override_model
        ? call<Object>(0x186b360, string(session.debug.model), nullptr) : field_bundle(member);
    if (!bundle) return;
    session.species = override_model ? 0 : call<int>(0x2044240, member, nullptr);
    session.renderer.set(renderer);
    session.visible = call<bool>(0x269a040, renderer, nullptr);
    session.bundle.set(bundle);
    session.request.set(request_bundle(bundle));
    if (!session.request.get()) {
        unload(session.bundle.get());
        session.bundle.clear();
        return;
    }
    session.phase = Phase::Loading;
    if (session.boarding) set_original_visibility(renderer, false);
    log(traversal_move == 431 ? "HiddenMoves: loading first party Rock Climb user's field model\n"
        : traversal_move == 127 ? "HiddenMoves: loading first party Waterfall user's field model\n"
                             : "HiddenMoves: loading first party Surf user's field model\n");
}

bool traversal_active(Object player) {
    return traversal_move == 431 || call<bool>(0x1dac820, player, nullptr);
}

void select_traversal(int move) {
    if (traversal_move == move) return;
    traversal_move = move;
    // The same party member can know several moves. Keep its visual and graph.
    const auto& config = debug_mount::state.config;
    if (session.phase == Phase::Ready &&
        ((config.enabled && std::strcmp(config.model, "party")) ||
         (session.member.get() && session.member.get() == first_user(move)))) {
        apply_placement(); // A shared user can have different water/cliff placements.
        return;
    }
    Object player = session.owner.get();
    if (player) stop();
    if (!player && move == 431) player = call<Object>(0x1f0a9e0, nullptr);
    if (alive(player) && traversal_active(player)) begin(player);
}

void poll() {
    Object request = session.request.get();
    if (!request || waiting(request)) return;
    if (session.phase == Phase::Retiring) {
        finish_request();
        return;
    }
    if (session.phase != Phase::Loading) return;
    Object player = session.owner.get();
    Object renderer = session.renderer.get();
    if (!alive(player) || !alive(renderer)) {
        stop();
        return;
    }
    Object anchor = field<Object>(player, SurfTransform);
    Object prefab = requested_prefab(request);
    if (!alive(anchor) || !alive(prefab)) {
        session.request.clear();
        unload(session.bundle.get());
        session.bundle.clear();
        session.phase = Phase::Failed;
        set_original_visibility(renderer, session.visible);
        log("HiddenMoves: asset/anchor unavailable; keeping Bibarel\n");
        return;
    }
    Object model = call<Object>(0x268ae00, prefab, anchor, false, nullptr);
    if (!alive(model)) {
        session.phase = Phase::Failed;
        set_original_visibility(renderer, session.visible);
        return;
    }
    session.model.set(model);
    // An independent visual must not join the field entity movement/collision
    // loop, which otherwise overwrites its parented position every frame.
    Object entity = component(model, "FieldPokemonEntity, Assembly-CSharp");
    if (!alive(entity)) {
        destroy(model);
        session.model.clear();
        session.phase = Phase::Failed;
        set_original_visibility(renderer, session.visible);
        log("HiddenMoves: expected field entity missing; keeping Bibarel\n");
        return;
    }
    call<void>(0x26a3450, entity, false, nullptr);
    // FieldPokemonEntity.OnDisable destroys its PlayableGraph. Rebuild the
    // visual graph after disabling simulation, then advance it ourselves.
    Object animator = component(model, "UnityEngine.Animator, UnityEngine.AnimationModule");
    Object animation = field<Object>(entity, 0xe0);
    if (alive(animator) && animation) {
        call<void>(0x211e160, animation, animator, nullptr);
        session.animation.set(animation);
        int idle = call<int>(0x1db8de0, entity, nullptr);
        call<void>(0x211e9b0, animation, idle, 0.0f, 0.0f, nullptr);
        call<void>(0x211eea0, animation, 0.0f, nullptr);
    }
    // Don't hide the vanilla mount unless a drawable mesh actually loaded.
    Object skins = children(model, "UnityEngine.SkinnedMeshRenderer, UnityEngine.CoreModule");
    size_t meshes = 0;
    for (size_t i = 0; i < array_length(skins); ++i) {
        Object skin = array_item(skins, i);
        if (!alive(skin) || !alive(call<Object>(0x2996b90, skin, nullptr))) continue;
        ++meshes;
        set_original_visibility(skin, true);
        call<void>(0x2996aa0, skin, true, nullptr);
    }
    if (!meshes) {
        // stop also releases the visual graph and loaded bundle.
        stop();
        session.owner.set(player);
        session.phase = Phase::Failed;
        log("HiddenMoves: no drawable meshes; keeping Bibarel\n");
        return;
    }
    apply_placement();
    session.request.clear();
    session.phase = Phase::Ready;
    update_visibility();
    log("HiddenMoves: traversal replacement attached\n");
    trace_climb_model();
}

HOOK_DEFINE_TRAMPOLINE(RendererVisibility) {
    static void Callback(Object renderer, bool visible, void* method) {
        if (renderer == session.renderer.get() && session.owner.get()) {
            const bool changed = session.visible != visible;
            session.visible = visible;
            if (session.phase == Phase::Loading && session.boarding) {
                Orig(renderer, false, method);
                return;
            }
            if (session.phase == Phase::Ready && alive(session.model.get())) {
                active(session.model.get(), visible);
                Orig(renderer, false, method);
                if (changed) trace_climb_model();
                return;
            }
        }
        Orig(renderer, visible, method);
    }
};
void set_original_visibility(Object renderer, bool visible) {
    RendererVisibility::Orig(renderer, visible, nullptr);
}
void update_visibility() {
    if (session.phase != Phase::Ready) return;
    active(session.model.get(), session.visible && alive(session.owner.get()));
    set_original_visibility(session.renderer.get(), false);
}

int traversal_cut_in = 0;
HOOK_DEFINE_TRAMPOLINE(CutInCommand) {
    static bool Callback(Object manager, void* method) {
        // EvCmdCutIn's second argument is an EvData.Aregment value (8 bytes).
        Object args = field<Object>(manager, 0x4c0);
        int move = 0;
        if (array_length(args) > 1) {
            int type = field<int>(args, 0x28);
            if (type == 1) move = static_cast<int>(field<float>(args, 0x2c));
            else if (type == 2) move = call<int>(0x2ccaca0, field<int>(args, 0x2c), nullptr);
        }
        const int previous = traversal_cut_in;
        traversal_cut_in = move == 57 || move == 127 || move == 431 ? move : 0;
        if (traversal_cut_in) debug_mount::update(0.5f);
        if (traversal_cut_in == 127 || traversal_cut_in == 431) select_traversal(traversal_cut_in);
        bool result = Orig(manager, method);
        traversal_cut_in = previous;
        return result;
    }
};
HOOK_DEFINE_TRAMPOLINE(CutInLoad) {
    static void Callback(Object cut_in, int species, void* method) {
        if (traversal_cut_in) {
            const auto& config = debug_mount::state.config;
            if (config.enabled && std::strcmp(config.model, "party")) {
                const char* s = config.model;
                const int selected_species = (s[2]-'0')*1000 + (s[3]-'0')*100 + (s[4]-'0')*10 + s[5]-'0';
                // Load(MonsNo) assumes female sex. Genderless and male-only
                // species have no such catalog row, and Load dereferences it.
                // Resolve a supported base appearance before invoking Load.
                const int sexes[] = {1, 0, 2};
                for (int sex : sexes) {
                    const int id = selected_species * 10000 + sex * 10;
                    if (!call<Object>(0x2cccf40, id, nullptr)) continue;
                    if (!call<Object>(0x2cc8450, cut_in, id, nullptr)) continue;
                    call<void>(0x2cc74c0, cut_in, selected_species,
                               static_cast<uint16_t>(0), sex, false, nullptr);
                    log("HiddenMoves: traversal debug cut-in uses validated catalog appearance\n");
                    return;
                }
                log("HiddenMoves: debug cut-in appearance unavailable; keeping vanilla preview\n");
            } else if (Object member = first_user(traversal_cut_in)) {
                // Let the game's PokemonParam overload preserve form/sex/shiny,
                // animation selection, cut-in framing, and request lifetime.
                call<void>(0x2cc7620, cut_in, member, nullptr);
                log(traversal_cut_in == 431 ? "HiddenMoves: Rock Climb cut-in uses first party Rock Climb user\n"
                    : traversal_cut_in == 127 ? "HiddenMoves: Waterfall cut-in uses first party Waterfall user\n"
                                           : "HiddenMoves: Surf cut-in uses first party Surf user\n");
                return;
            }
        }
        Orig(cut_in, species, method);
    }
};

HOOK_DEFINE_TRAMPOLINE(WaterfallCommand) {
    static bool Callback(Object manager, void* method) {
        select_traversal(127);
        const bool complete = Orig(manager, method);
        if (complete) select_traversal(57);
        return complete;
    }
};

HOOK_DEFINE_TRAMPOLINE(RockClimbCommand) {
    static bool Callback(Object manager, void* method) {
        select_traversal(431);
        // Unlike Waterfall, climbing starts on land and never sets IsSwim.
        // Also handle commands reached without a preceding cut-in.
        if (session.phase == Phase::Empty) begin(call<Object>(0x1f0a9e0, nullptr));
        const bool complete = Orig(manager, method);
        if (complete) {
            stop(); // The command has hidden Bibarel before completing.
            traversal_move = 57;
        }
        return complete;
    }
};

HOOK_DEFINE_TRAMPOLINE(TraversalMessage) {
    static void Callback(Object parser, Object label, int language, void* method) {
        // These English success labels are literal wild-Bibarel messages.
        // Clone per use so the resident message asset and vanilla fallback
        // remain intact. Keep the normal parser's style and end-event data.
        int move = 0;
        if (label && language == 2) {
            Object name = field<Object>(label, 0x18);
            if (string_equals(name, "97-msg_taki_02")) move = 127;
            else if (string_equals(name, "97-msg_naminori_02")) move = 57;
            else if (string_equals(name, "97-msg_rock_02")) move = 431;
        }
        const auto& config = debug_mount::state.config;
        const bool debug_model = config.enabled && std::strcmp(config.model, "party");
        Object member = move && !debug_model ? first_user(move) : nullptr;
        Object words = member ? field<Object>(label, 0x38) : nullptr;
        if (!member || array_length(words) != 1 || !array_item(words, 0)) {
            Orig(parser, label, language, method);
            return;
        }
        ScopedRoot name, suffix, text, copy, copied_words, word;
        name.set(call<Object>(0x2048e80, member, nullptr));
        if (!name.get() || field<int>(name.get(), 0x10) <= 0) {
            Orig(parser, label, language, method);
            return;
        }
        suffix.set(string(move == 431 ? " helped out by using Rock Climb!"
            : move == 127 ? " helped out by using Waterfall!" : " helped out by using Surf!"));
        text.set(call<Object>(0x26ef430, name.get(), suffix.get(), nullptr));
        copy.set(call<Object>(0x26d1390, label, nullptr));
        copied_words.set(call<Object>(0x2757e60, words, nullptr));
        word.set(call<Object>(0x26d1390, array_item(words, 0), nullptr));
        Object copied_word = word.get();
        if (!text.get() || !copy.get() || !copied_words.get() || !copied_word) {
            Orig(parser, label, language, method);
            return;
        }
        store_object(copied_word, 0x20, text.get());
        *reinterpret_cast<float*>(reinterpret_cast<uintptr_t>(copied_word) + 0x28) =
            call<float>(0x210a7a0, language, text.get(), 1.0f, nullptr);
        store_object(copied_words.get(), 0x20, copied_word);
        store_object(copy.get(), 0x38, copied_words.get());
        Orig(parser, copy.get(), language, method);
        log("HiddenMoves: traversal message names selected party Pokemon\n");
    }
};

HOOK_DEFINE_TRAMPOLINE(SurfAppear) {
    static void Callback(Object player, float offset, float time, void* method) {
        if (session.owner.get() && session.owner.get() != player) stop();
        traversal_move = 57;
        begin(player);
        Orig(player, offset, time, method);
    }
};
HOOK_DEFINE_TRAMPOLINE(SwimState) {
    static void Callback(Object player, bool swimming, void* method) {
        // Dismount restores the original presentation before changing state.
        if (!swimming && session.owner.get() == player) { stop(); traversal_move = 57; }
        Orig(player, swimming, method);
        if (session.owner.get() == player) update_visibility();
    }
};
HOOK_DEFINE_TRAMPOLINE(PlayerLate) {
    static void Callback(Object player, float delta, void* method) {
        Orig(player, delta, method);
        if (session.owner.get() && !alive(session.owner.get())) { stop(); traversal_move = 57; }
        poll();
        Object current = call<Object>(0x1f0a9e0, nullptr);
        if (current != player) return;
        debug_mount::update(delta);
        if (debug_revision != debug_mount::state.revision) {
            debug_revision = debug_mount::state.revision;
            if (session.owner.get() == player) {
                if (session.phase == Phase::Ready && debug_mount::same_model(session.debug, debug_mount::state.config)) {
                    session.debug = debug_mount::state.config;
                    apply_placement(); // Position/scale edits don't reload assets.
                } else stop(); // Pending requests retire before the next model loads.
            }
        }
        if (session.owner.get() && session.owner.get() != player) { stop(); traversal_move = 57; }
        if (session.phase == Phase::Empty && traversal_active(player)) {
            begin(player); // Covers saves on water and canceled loads during a climb.
        }
        if (session.phase == Phase::Ready && !alive(session.model.get())) stop();
        update_visibility();
        if (session.phase == Phase::Ready && session.visible && session.animation.get()) {
            call<void>(0x211eea0, session.animation.get(), delta, nullptr);
        }
    }
};
HOOK_DEFINE_TRAMPOLINE(CharacterOff) {
    static void Callback(Object character, void* method) {
        if (session.owner.get() == character) { stop(); traversal_move = 57; }
        Orig(character, method);
    }
};
}

extern "C" void exl_main(void*, void*) {
    // Compare native signatures before modifying executable memory. This also
    // prevents installing hooks over another mod's changes to these entrypoints.
    if (!supported_game()) {
        log("HiddenMoves: unsupported executable; no hooks installed\n");
        return;
    }
    exl::hook::Initialize();
    RendererVisibility::InstallAtOffset(game::RendererEnabled);
    SurfAppear::InstallAtOffset(game::AppearSwim);
    SwimState::InstallAtOffset(game::ChangeSwim);
    PlayerLate::InstallAtOffset(game::PlayerLateUpdate);
    CharacterOff::InstallAtOffset(game::CharacterDisable);
    CutInCommand::InstallAtOffset(0x2c6dc40);
    CutInLoad::InstallAtOffset(0x2cc74b0);
    WaterfallCommand::InstallAtOffset(0x2c6cd40);
    RockClimbCommand::InstallAtOffset(0x2c6b1f0);
    TraversalMessage::InstallAtOffset(0x1f96e90);
    log("HiddenMoves: BD 1.3.0 Surf/Waterfall/Rock Climb prototype initialized\n");
}

extern "C" void exl_exception_entry() {
    EXL_ABORT(0x484d);
}
