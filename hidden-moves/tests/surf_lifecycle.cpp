// Run the actual native session and hooks against a controlled engine boundary.
#include <array>
#include <algorithm>
#include <cassert>
#include <cstring>
#include <iostream>
#include <map>
#include <memory>
#include <vector>
#include "../native/main.cpp"
#include "../native/debug_config.cpp"

std::string debug_file;
namespace nn::fs {
Result MountSdCardForDebug(const char*) { return {0}; }
Result OpenFile(FileHandle*, const char*, int) { return {debug_file.empty() ? 1u : 0u}; }
Result GetFileSize(long* size, FileHandle) { *size = debug_file.size(); return {0}; }
Result ReadFile(FileHandle, long, void* buffer, unsigned long size) {
    std::memcpy(buffer, debug_file.data(), size); return {0};
}
void CloseFile(FileHandle) {}
}

struct Managed {
    alignas(8) std::array<unsigned char, 2048> data{};
    bool living = true, enabled = true, egg = false, surf = false, waterfall = false, rock_climb = false;
    int species = 0;
    game::Vector3 position{}, rotation{}, scale{};
};
std::map<void*, std::unique_ptr<Managed>> objects;
std::map<int, void*> handles;
std::vector<void*> party;
void *player, *renderer, *anchor, *bundle, *request, *item, *cache, *prefab;
void *model, *entity, *transform, *catalog, *animator, *animation, *skins, *skin, *mesh;
void *selected = nullptr, *parented_to = nullptr;
bool pending = true, swimming = true, missing_prefab = false, missing_entity = false;
bool missing_mesh = false, graph_ready = false, offscreen_updates = false;
const char* requested_type = "";
int graph_initializations = 0, animation_ticks = 0, graph_destructions = 0;
void* preview_member = nullptr;
int preview_species = 0;
int preview_catalog_id = -1, preview_sex = -1;
bool missing_preview_params = false;
bool waterfall_complete = false;
bool rock_climb_complete = false, rock_climb_visible = false;
bool dialogue_mode = false;
void load_preview(void*, void* member, void*) { preview_member = member; }
void load_debug_preview(void*, int species, uint16_t form, int sex, bool rare, void*) {
    assert(form == 0 && !rare);
    assert(species * 10000 + sex * 10 == preview_catalog_id);
    preview_species = species; preview_sex = sex;
}
void* preview_params(void*, int id, void*) {
    assert(id == preview_catalog_id);
    return missing_preview_params ? nullptr : catalog;
}
int work_value(int index, void*) { assert(index == 3); return 57; }
int next_handle = 1, unloads = 0, loads = 0, instantiations = 0;

void* make() {
    auto node = std::make_unique<Managed>();
    void* ptr = node->data.data();
    objects.emplace(ptr, std::move(node));
    return ptr;
}
Managed& node(void* ptr) { return *objects.at(ptr); }
void pointer(void* obj, size_t offset, void* value) {
    std::memcpy(static_cast<unsigned char*>(obj) + offset, &value, sizeof(value));
}
void* make_text(std::u16string_view value) {
    void* obj = make(); int length = value.size();
    std::memcpy(static_cast<char*>(obj)+0x10, &length, sizeof(length));
    std::memcpy(static_cast<char*>(obj)+0x14, value.data(), value.size()*2);
    return obj;
}
std::u16string text_value(void* value) {
    return {reinterpret_cast<char16_t*>(static_cast<char*>(value)+0x14),
            static_cast<size_t>(game::field<int>(value, 0x10))};
}
void* clone_object(void* obj, void*) {
    void* copy = make(); node(copy).data = node(obj).data; return copy;
}
void* nickname(void* member, void*) { return game::field<void*>(member, 0x80); }
void* concat_text(void* a, void* b, void*) { return make_text(text_value(a)+text_value(b)); }
float text_width(int language, void* text, float scale, void*) {
    assert(language == 2 && scale == 1); return text_value(text).size()*10;
}
void write_barrier(void** slot, void* value) { assert(*slot == value); }
void mock_message_original(void* parser, void* label, int, void*) { pointer(parser, 0x30, label); }
bool live(void* obj, void*) { return obj && node(obj).living; }
game::Handle retain(void* obj, void*) {
    int value = next_handle++;
    handles[value] = obj;
    return {value};
}
void* target(int handle, void*) { return handles.at(handle); }
void release(int handle, void*) { assert(handles.erase(handle) == 1); }
void* get_party(void*) { return catalog; }
uint32_t count(void*, void*) { return party.size(); }
void* member(void*, uint32_t index, void*) { return party.at(index); }
bool is_null(void*, void*) { return false; }
bool egg(void* obj, int type, void*) { assert(type == 2); return node(obj).egg; }
bool knows(void* obj, int move, void*) {
    assert(move == 57 || move == 127 || move == 431);
    return move == 57 ? node(obj).surf : move == 127 ? node(obj).waterfall : node(obj).rock_climb;
}
int unique(void* obj, void*) { selected = obj; return 1; }
int species(void* obj, void*) { return node(obj).species; }
void* get_catalog(int id, void*) {
    return id == 1 || id == preview_catalog_id ? catalog : nullptr;
}
void* bundle_name(void* obj, void*) { assert(obj == bundle); return bundle; }
void* load(void* obj, bool all, void*, void*, void*) {
    assert(obj == bundle && all); ++loads; return request;
}
void* dispatch(void*, void*) { return request; }
bool mock_wait(void*, void*) { return pending; }
void* bundle_request(void*, void*) { return item; }
void* first_asset(void*, void*) { return missing_prefab ? nullptr : prefab; }
int mock_unload(void*, void*) { ++unloads; return 0; }
void* create_string(void*, const char* name, void*) {
    requested_type = name;
    if (!dialogue_mode) return bundle;
    std::u16string value;
    while (*name) value.push_back(*name++);
    return make_text(value);
}
void* get_type(void*, void*) { return catalog; }
void* get_component(void*, void*, void*) {
    if (std::string_view(requested_type).starts_with("UnityEngine.Animator")) return animator;
    return missing_entity ? nullptr : entity;
}
void* get_children(void*, void*, bool inactive, void*) { assert(inactive); return skins; }
void* shared_mesh(void*, void*) { return missing_mesh ? nullptr : mesh; }
void set_offscreen(void*, bool value, void*) { offscreen_updates = value; }
void init_graph(void* obj, void* target, void*) {
    assert(obj == animation && target == animator && !node(entity).enabled);
    graph_ready = true; ++graph_initializations;
}
void destroy_graph(void* obj, void*) {
    assert(obj == animation && graph_ready); graph_ready = false; ++graph_destructions;
}
int idle_index(void*, void*) { return 0; }
void play(void*, int index, float, float, void*) { assert(graph_ready && index == 0); }
void advance(void*, float, void*) { assert(graph_ready); ++animation_ticks; }
void* instantiate(void* original, void* parent, bool world, void*) {
    assert(original == prefab && !world);
    parented_to = parent; ++instantiations;
    model = make(); entity = make(); transform = make();
    animator = make(); animation = make(); skins = make(); skin = make(); mesh = make();
    pointer(entity, 0xe0, animation);
    size_t length = 1;
    std::memcpy(static_cast<unsigned char*>(skins) + 0x18, &length, sizeof(length));
    pointer(skins, 0x20, skin);
    graph_ready = true; // FieldPokemonEntity.OnEnable initializes its graph.
    return model;
}
void* get_transform(void* obj, void*) { assert(obj == model); return transform; }
void set_position(void* obj, game::Vector3 value, void*) { node(obj).position = value; }
void set_rotation(void* obj, game::Vector3 value, void*) { node(obj).rotation = value; }
void set_scale(void* obj, game::Vector3 value, void*) { node(obj).scale = value; }
game::Vector3 get_position(void* obj, void*) { return node(obj).position; }
game::Vector3 get_scale(void* obj, void*) { return node(obj).scale; }
void mock_active(void* obj, bool value, void*) {
    node(obj).enabled = value;
    if (obj == entity && !value) graph_ready = false; // OnDisable destroys it.
}
void mock_destroy(void* obj, void*) { node(obj).living = false; }
bool enabled(void* obj, void*) { return node(obj).enabled; }
void* current(void*) { return player; }
bool is_swim(void*, void*) { return swimming; }

uintptr_t mock_address(uintptr_t rva) {
#define ADDRESS(offset, fn) case offset: return reinterpret_cast<uintptr_t>(&fn)
    switch (rva) {
        ADDRESS(0x268a7d0, live); ADDRESS(0x22c6410, retain);
        ADDRESS(0x22c62b0, target); ADDRESS(0x22c6510, release);
        ADDRESS(0x2ce2b50, get_party); ADDRESS(0x2056af0, count);
        ADDRESS(0x20556f0, member); ADDRESS(0x204c9d0, is_null);
        ADDRESS(0x2049370, egg); ADDRESS(0x2045ea0, knows);
        ADDRESS(0x2044240, species); ADDRESS(0x2ccd050, unique);
        ADDRESS(0x2cccf40, get_catalog); ADDRESS(0x186b360, bundle_name);
        ADDRESS(0x22dbfb0, load); ADDRESS(0x22dc320, dispatch);
        ADDRESS(0x22e7d80, mock_wait); ADDRESS(0x22e7b70, bundle_request);
        ADDRESS(0x22d6960, first_asset); ADDRESS(0x22dbde0, mock_unload);
        ADDRESS(0x26fb3e0, create_string); ADDRESS(0x2b1e1d0, get_type);
        ADDRESS(0x26a8240, get_component); ADDRESS(0x268ae00, instantiate);
        ADDRESS(0x26b1710, get_children); ADDRESS(0x2996b90, shared_mesh);
        ADDRESS(0x2996aa0, set_offscreen); ADDRESS(0x211e160, init_graph);
        ADDRESS(0x211e7b0, destroy_graph); ADDRESS(0x1db8de0, idle_index);
        ADDRESS(0x211e9b0, play); ADDRESS(0x211eea0, advance);
        ADDRESS(0x26b18d0, get_transform); ADDRESS(0x299d3d0, set_position);
        ADDRESS(0x299d770, set_rotation); ADDRESS(0x299e000, set_scale);
        ADDRESS(0x299d1c0, get_position); ADDRESS(0x299f5c0, get_scale);
        ADDRESS(0x26b1a60, enabled);
        ADDRESS(0x26a3450, mock_active); ADDRESS(0x26b19c0, mock_active);
        ADDRESS(0x268b1f0, mock_destroy); ADDRESS(0x269a040, enabled);
        ADDRESS(0x1f0a9e0, current); ADDRESS(0x1dac820, is_swim);
        ADDRESS(0x2cc7620, load_preview);
        ADDRESS(0x2cc74c0, load_debug_preview);
        ADDRESS(0x2cc8450, preview_params);
        ADDRESS(0x2ccaca0, work_value);
        ADDRESS(0x26d1390, clone_object); ADDRESS(0x2757e60, clone_object);
        ADDRESS(0x2048e80, nickname); ADDRESS(0x26ef430, concat_text);
        ADDRESS(0x210a7a0, text_width); ADDRESS(0x2afa20, write_barrier);
    }
#undef ADDRESS
    std::cerr << "Unexpected RVA " << std::hex << rva << '\n';
    std::abort();
}
void mock_original(const char* name, void* obj, bool value, void*) {
    if (std::string_view(name) == "RendererVisibility") node(obj).enabled = value;
    if (std::string_view(name) == "SwimState") swimming = value;
}
void mock_original(const char*, void*, float, float, void*) {}
void mock_original(const char*, void*, float, void*) {}
void mock_original(const char*, void*, void*) {}
void mock_original(const char*, void*, int species, void*) { preview_species = species; }
bool mock_cut_in_original(void* manager, void*) {
    CutInLoad::Callback(manager, 399, nullptr); return true;
}
bool mock_waterfall_original(void*, void*) { return waterfall_complete; }
bool mock_rock_climb_original(void*, void*) {
    RendererVisibility::Callback(renderer, rock_climb_visible && !rock_climb_complete, nullptr);
    return rock_climb_complete;
}

void reset() {
    assert(handles.empty());
    objects.clear(); party.clear();
    player = make(); renderer = make(); anchor = make(); bundle = make();
    request = make(); item = make(); cache = make(); prefab = make(); catalog = make();
    pointer(player, game::BibarelRenderer, renderer);
    pointer(player, game::SurfTransform, anchor);
    pointer(item, 0x48, cache); pointer(catalog, 0x28, bundle);
    pending = true; swimming = true; missing_prefab = false; missing_entity = false;
    selected = nullptr; model = nullptr; parented_to = nullptr;
    loads = 0; unloads = 0; instantiations = 0;
    missing_mesh = false; graph_ready = false; offscreen_updates = false;
    graph_initializations = 0; graph_destructions = 0; animation_ticks = 0;
    debug_mount::state = {}; debug_revision = 0; debug_file.clear();
    traversal_cut_in = 0; traversal_move = 57;
    preview_member = nullptr; preview_species = 0;
    preview_catalog_id = -1; preview_sex = -1; missing_preview_params = false;
    waterfall_complete = false;
    rock_climb_complete = false; rock_climb_visible = false;
    dialogue_mode = false;
}
void* pokemon(int number, bool surf, bool egg = false) {
    void* value = make(); node(value).species = number;
    node(value).surf = surf; node(value).egg = egg;
    party.push_back(value); return value;
}
void tick() { PlayerLate::Callback(player, 0.016f, nullptr); }
void start() { SurfAppear::Callback(player, 1.0f, 0.5f, nullptr); }
void end() { SwimState::Callback(player, false, nullptr); }

int main() {
    reset();
    pokemon(25, false); pokemon(130, true, true);
    auto* gyarados = pokemon(130, true); pokemon(419, true);
    start();
    assert(selected == gyarados && loads == 1 && node(renderer).enabled);
    tick(); assert(instantiations == 0); // Don't hide Bibarel while loading.
    pending = false; tick();
    assert(session.phase == Phase::Ready && parented_to == anchor);
    assert(!node(renderer).enabled && node(model).enabled && !node(entity).enabled);
    assert(node(transform).scale.x == placement_for(130).scale.x);
    // The anchor is one unit below the water: compensate that local offset.
    assert(node(transform).position.y == placement_for(130).offset.y);
    assert(graph_initializations == 1 && graph_ready && animation_ticks > 0);
    assert(offscreen_updates && node(skin).enabled);
    RendererVisibility::Callback(renderer, false, nullptr);
    assert(!node(model).enabled);
    RendererVisibility::Callback(renderer, true, nullptr);
    assert(node(model).enabled && !node(renderer).enabled);
    // Reordering mid-traversal must not select a different model.
    std::reverse(party.begin(), party.end()); tick();
    assert(selected == gyarados && loads == 1);
    end();
    assert(node(renderer).enabled && !node(model).living && unloads == 1 && handles.empty());
    assert(graph_destructions == 1 && !graph_ready);

    reset(); pokemon(25, false); start(); tick();
    assert(loads == 0 && node(renderer).enabled); end(); assert(handles.empty());

    reset(); pokemon(130, true); start(); end();
    assert(session.phase == Phase::Retiring && unloads == 0);
    tick(); assert(instantiations == 0 && unloads == 0);
    pending = false; tick(); assert(unloads == 1 && handles.empty());

    reset(); pokemon(130, true); start(); pending = false; missing_prefab = true; tick();
    assert(session.phase == Phase::Failed && node(renderer).enabled && unloads == 1);
    tick(); assert(loads == 1); end(); assert(unloads == 1 && handles.empty());

    reset(); pokemon(130, true); start(); pending = false; missing_mesh = true; tick();
    assert(session.phase == Phase::Failed && node(renderer).enabled && !node(model).living);
    assert(graph_destructions == 1 && unloads == 1);
    tick(); assert(loads == 1); end(); assert(handles.empty());

    reset(); pokemon(130, true); start(); pending = false; tick();
    CharacterOff::Callback(player, nullptr);
    assert(!node(model).living && handles.empty());

    reset(); pokemon(130, true); pending = false;
    tick(); tick(); // A save loaded on water has no AppearSwim call.
    assert(session.phase == Phase::Ready && loads == 1); end(); assert(handles.empty());

    // File edits are consumed while surfing; placement-only changes retain
    // the same instance. Model swaps retire pending requests safely.
    reset(); pokemon(130, true); pending = false;
    debug_file = "enabled=1\nmodel=pm0130_00_00\noffset=0,-0.3,0.1\nrotation=0,0,0\nscale=0.7,0.7,0.7\n";
    tick(); tick(); assert(session.phase == Phase::Ready);
    auto original_model = model;
    debug_file = "enabled=1\nmodel=pm0130_00_00\noffset=0,-1,0.1\nrotation=0,90,0\nscale=1,1,1\n";
    PlayerLate::Callback(player, 0.6f, nullptr);
    assert(model == original_model && node(transform).position.y == -1 && node(transform).scale.x == 1);
    debug_file = "enabled=1\nmodel=pm0130_00_00\noffset=0,NaN,0\nrotation=0,0,0\nscale=1,1,1\n";
    PlayerLate::Callback(player, 0.6f, nullptr);
    assert(model == original_model && node(transform).position.y == -1);
    debug_file = "enabled=1\nmodel=pm0131_00_00\noffset=0,0,0\nrotation=0,0,0\nscale=1,1,1\n";
    pending = true; PlayerLate::Callback(player, 0.6f, nullptr);
    assert(!node(original_model).living && session.phase == Phase::Loading);
    debug_file = "enabled=0\n";
    PlayerLate::Callback(player, 0.6f, nullptr);
    assert(session.phase == Phase::Retiring);
    pending = false; tick(); tick();
    assert(session.phase == Phase::Ready && selected == party[0] && !session.debug.enabled);
    // A disabled config is no longer polled; traversal cut-ins still read edits.
    debug_file = "enabled=1\nmodel=pm0130_00_00\noffset=0,0,0\nrotation=0,0,0\nscale=1,1,1\n";
    PlayerLate::Callback(player, 0.6f, nullptr);
    assert(!debug_mount::state.config.enabled);
    debug_mount::refresh();
    assert(debug_mount::state.config.enabled);
    end(); assert(handles.empty());

    debug_mount::Config parsed;
    auto parse_text = [&](std::string text) { return debug_mount::parse(text.data(), parsed); };
    assert(parse_text("enabled=0\n"));
    assert(!parse_text("enabled=1\n"));
    assert(!parse_text("enabled=0\nenabled=0\n"));
    assert(!parse_text("enabled=0\nmodel=../../main\n"));
    assert(!parse_text("enabled=0\nscale=0,1,1\n"));

    reset(); auto* chosen = pokemon(130, true); swimming = false; pending = false;
    start(); tick();
    assert(session.phase == Phase::Ready && node(model).enabled && !node(renderer).enabled);
    RendererVisibility::Callback(renderer, false, nullptr);
    assert(!node(model).enabled && !node(renderer).enabled);
    RendererVisibility::Callback(renderer, true, nullptr);
    assert(node(model).enabled && !node(renderer).enabled);
    SwimState::Callback(player, true, nullptr);
    assert(node(model).enabled && !node(renderer).enabled);
    end(); assert(handles.empty());

    reset(); pokemon(130, true); swimming = false;
    start(); assert(session.phase == Phase::Loading && !node(renderer).enabled);
    RendererVisibility::Callback(renderer, true, nullptr);
    assert(!node(renderer).enabled);
    missing_prefab = true; pending = false; tick();
    assert(session.phase == Phase::Failed && node(renderer).enabled);
    end(); assert(handles.empty());

    reset(); chosen = pokemon(130, true);
    auto* manager = make(); auto* arguments = make();
    pointer(manager, 0x4c0, arguments);
    size_t argc = 2; int type = 1; float move = 57;
    std::memcpy(static_cast<char*>(arguments)+0x18, &argc, sizeof(argc));
    std::memcpy(static_cast<char*>(arguments)+0x28, &type, sizeof(type));
    std::memcpy(static_cast<char*>(arguments)+0x2c, &move, sizeof(move));
    assert(CutInCommand::Callback(manager, nullptr));
    assert(preview_member == chosen && !traversal_cut_in);
    preview_member = nullptr; type = 2; int work_index = 3;
    std::memcpy(static_cast<char*>(arguments)+0x28, &type, sizeof(type));
    std::memcpy(static_cast<char*>(arguments)+0x2c, &work_index, sizeof(work_index));
    CutInCommand::Callback(manager, nullptr);
    assert(preview_member == chosen && !traversal_cut_in);
    preview_member = nullptr; move = 70; // Strength's preview remains vanilla.
    type = 1;
    std::memcpy(static_cast<char*>(arguments)+0x28, &type, sizeof(type));
    std::memcpy(static_cast<char*>(arguments)+0x2c, &move, sizeof(move));
    CutInCommand::Callback(manager, nullptr);
    assert(!preview_member && preview_species == 399);
    move = 57;
    std::memcpy(static_cast<char*>(arguments)+0x2c, &move, sizeof(move));
    debug_mount::state.config.enabled = true;
    std::strcpy(debug_mount::state.config.model, "pm0384_00_00");
    preview_catalog_id = 3840020; // Rayquaza: only genderless entries exist.
    CutInCommand::Callback(manager, nullptr);
    assert(preview_species == 384 && preview_sex == 2);
    std::strcpy(debug_mount::state.config.model, "pm0034_00_00");
    preview_catalog_id = 340000; // Nidoking: only male entries exist.
    CutInCommand::Callback(manager, nullptr);
    assert(preview_species == 34 && preview_sex == 0);
    std::strcpy(debug_mount::state.config.model, "pm0130_00_00");
    preview_catalog_id = 1300010;
    CutInCommand::Callback(manager, nullptr);
    assert(preview_species == 130 && preview_sex == 1);
    missing_preview_params = true;
    CutInCommand::Callback(manager, nullptr);
    assert(preview_species == 399); // Missing framing data falls back safely.
    missing_preview_params = false;
    preview_catalog_id = -1;
    CutInCommand::Callback(manager, nullptr);
    assert(preview_species == 399); // Missing catalog also falls back safely.

    reset(); auto* surf_user = pokemon(130, true);
    auto* egg_user = pokemon(118, false, true); node(egg_user).waterfall = true;
    auto* waterfall_user = pokemon(119, false); node(waterfall_user).waterfall = true;
    auto* later_user = pokemon(160, true); node(later_user).waterfall = true;
    pending = false; start(); tick();
    assert(session.member.get() == surf_user);
    assert(!WaterfallCommand::Callback(nullptr, nullptr)); tick();
    assert(traversal_move == 127 && session.member.get() == waterfall_user);
    assert(session.phase == Phase::Ready && session.species == 119);
    const int same_loads = loads;
    WaterfallCommand::Callback(nullptr, nullptr); tick();
    assert(loads == same_loads); // Repeated command frames don't reload.
    waterfall_complete = true;
    assert(WaterfallCommand::Callback(nullptr, nullptr)); tick();
    assert(traversal_move == 57 && session.member.get() == surf_user);
    end(); assert(handles.empty());

    reset(); surf_user = pokemon(130, true); node(surf_user).waterfall = true;
    pending = false; start(); tick();
    const int both_loads = loads;
    WaterfallCommand::Callback(nullptr, nullptr); tick();
    assert(traversal_move == 127 && loads == both_loads);
    waterfall_complete = true; WaterfallCommand::Callback(nullptr, nullptr); tick();
    assert(traversal_move == 57 && loads == both_loads);
    end(); assert(handles.empty());

    reset(); surf_user = pokemon(130, true);
    pending = false; start(); tick();
    WaterfallCommand::Callback(nullptr, nullptr);
    assert(session.phase == Phase::Failed && node(renderer).enabled);
    waterfall_complete = true; WaterfallCommand::Callback(nullptr, nullptr); tick();
    assert(session.phase == Phase::Ready && session.member.get() == surf_user);
    end(); assert(handles.empty());

    reset(); surf_user = pokemon(130, true);
    waterfall_user = pokemon(119, false); node(waterfall_user).waterfall = true;
    start(); assert(session.phase == Phase::Loading);
    WaterfallCommand::Callback(nullptr, nullptr);
    assert(session.phase == Phase::Retiring);
    pending = false; tick(); tick();
    assert(session.phase == Phase::Ready && session.member.get() == waterfall_user);
    end(); assert(traversal_move == 57 && handles.empty());

    reset(); surf_user = pokemon(130, true);
    waterfall_user = pokemon(119, false); node(waterfall_user).waterfall = true;
    manager = make(); arguments = make(); pointer(manager, 0x4c0, arguments);
    move = 127;
    std::memcpy(static_cast<char*>(arguments)+0x18, &argc, sizeof(argc));
    std::memcpy(static_cast<char*>(arguments)+0x28, &type, sizeof(type));
    std::memcpy(static_cast<char*>(arguments)+0x2c, &move, sizeof(move));
    CutInCommand::Callback(manager, nullptr);
    assert(preview_member == waterfall_user && traversal_move == 127 && !traversal_cut_in);
    WaterfallCommand::Callback(manager, nullptr);
    waterfall_complete = true; WaterfallCommand::Callback(manager, nullptr);
    assert(traversal_move == 57);

    // Rock Climb starts on land, follows the helper's boarding/climbing
    // visibility, and releases the visual at the end instead of staying mounted.
    reset(); surf_user = pokemon(9, true); node(surf_user).rock_climb = true;
    pending = false; start(); tick();
    auto* shared_mount = model;
    const auto water_position = node(transform).position;
    select_traversal(431);
    assert(model == shared_mount && loads == 1);
    assert(node(transform).position.z == placement_for(9, 431).offset.z);
    assert(node(transform).position.z != water_position.z);
    select_traversal(57);
    assert(model == shared_mount && loads == 1 && node(transform).position.z == water_position.z);
    end(); assert(handles.empty());

    reset(); swimming = false; node(renderer).enabled = false;
    pokemon(130, true);
    egg_user = pokemon(400, false, true); node(egg_user).rock_climb = true;
    auto* climb_user = pokemon(67, false); node(climb_user).rock_climb = true;
    later_user = pokemon(68, false); node(later_user).rock_climb = true;
    assert(!RockClimbCommand::Callback(nullptr, nullptr));
    assert(traversal_move == 431 && selected == climb_user && loads == 1);
    rock_climb_visible = true;
    RockClimbCommand::Callback(nullptr, nullptr);
    assert(!node(renderer).enabled); // Suppress boarding while loading.
    pending = false; tick();
    assert(session.phase == Phase::Ready && parented_to == anchor);
    assert(session.member.get() == climb_user && node(model).enabled && !swimming);
    RockClimbCommand::Callback(nullptr, nullptr); tick(); assert(loads == 1);
    rock_climb_visible = false; RockClimbCommand::Callback(nullptr, nullptr);
    assert(!node(model).enabled);
    rock_climb_visible = true; RockClimbCommand::Callback(nullptr, nullptr);
    assert(node(model).enabled);
    rock_climb_complete = true;
    assert(RockClimbCommand::Callback(nullptr, nullptr)); tick();
    assert(traversal_move == 57 && session.phase == Phase::Empty && handles.empty());
    assert(!node(model).living && !node(renderer).enabled && loads == 1 && unloads == 1);

    reset(); swimming = false; node(renderer).enabled = false;
    pokemon(130, true); // No Rock Climb user: retain the vanilla helper.
    rock_climb_visible = true; RockClimbCommand::Callback(nullptr, nullptr); tick();
    assert(session.phase == Phase::Failed && loads == 0 && node(renderer).enabled);
    rock_climb_complete = true; RockClimbCommand::Callback(nullptr, nullptr);
    assert(handles.empty() && !node(renderer).enabled);

    reset(); swimming = false; node(renderer).enabled = false;
    climb_user = pokemon(67, false); node(climb_user).rock_climb = true;
    rock_climb_visible = true; RockClimbCommand::Callback(nullptr, nullptr);
    missing_prefab = true; pending = false; tick();
    assert(session.phase == Phase::Failed && node(renderer).enabled);
    rock_climb_complete = true; RockClimbCommand::Callback(nullptr, nullptr);
    assert(handles.empty());

    reset(); swimming = false; node(renderer).enabled = false;
    climb_user = pokemon(67, false); node(climb_user).rock_climb = true;
    RockClimbCommand::Callback(nullptr, nullptr);
    rock_climb_complete = true; RockClimbCommand::Callback(nullptr, nullptr);
    assert(session.phase == Phase::Retiring && traversal_move == 57 && unloads == 0);
    pending = false; tick(); tick();
    assert(session.phase == Phase::Empty && instantiations == 0 && unloads == 1 && handles.empty());

    reset(); swimming = false; node(renderer).enabled = false;
    climb_user = pokemon(67, false); node(climb_user).rock_climb = true;
    manager = make(); arguments = make(); pointer(manager, 0x4c0, arguments);
    move = 431; type = 1;
    std::memcpy(static_cast<char*>(arguments)+0x18, &argc, sizeof(argc));
    std::memcpy(static_cast<char*>(arguments)+0x28, &type, sizeof(type));
    std::memcpy(static_cast<char*>(arguments)+0x2c, &move, sizeof(move));
    CutInCommand::Callback(manager, nullptr);
    assert(preview_member == climb_user && traversal_move == 431 && loads == 1 && !traversal_cut_in);
    pending = false; tick(); assert(session.phase == Phase::Ready && !node(model).enabled);
    rock_climb_visible = true; RockClimbCommand::Callback(manager, nullptr);
    assert(node(model).enabled && loads == 1);
    CharacterOff::Callback(player, nullptr);
    assert(handles.empty() && traversal_move == 57 && !node(model).living);

    reset(); dialogue_mode = true;
    auto* user = pokemon(130, true); node(user).waterfall = true; node(user).rock_climb = true;
    pointer(user, 0x80, make_text(u"Gyárados"));
    auto* parser = make(); auto* label = make(); auto* words = make(); auto* word = make();
    pointer(label, 0x18, make_text(u"97-msg_taki_02"));
    pointer(label, 0x38, words);
    size_t word_count = 1;
    std::memcpy(static_cast<char*>(words)+0x18, &word_count, sizeof(word_count));
    pointer(words, 0x20, word);
    pointer(word, 0x20, make_text(u"A wild Bibarel helped out by using Waterfall!"));
    TraversalMessage::Callback(parser, label, 2, nullptr);
    auto* copy = game::field<void*>(parser, 0x30);
    auto* copied_word = game::array_item(game::field<void*>(copy, 0x38), 0);
    assert(copy != label && copied_word != word);
    assert(text_value(game::field<void*>(copied_word, 0x20)) == u"Gyárados helped out by using Waterfall!");
    assert(text_value(game::field<void*>(word, 0x20)) == u"A wild Bibarel helped out by using Waterfall!");
    assert(game::field<float>(copied_word, 0x28) > 0 && handles.empty());
    node(user).waterfall = false;
    TraversalMessage::Callback(parser, label, 2, nullptr);
    assert(game::field<void*>(parser, 0x30) == label);
    node(user).waterfall = true;
    TraversalMessage::Callback(parser, label, 3, nullptr);
    assert(game::field<void*>(parser, 0x30) == label);
    pointer(label, 0x18, make_text(u"97-msg_naminori_02"));
    TraversalMessage::Callback(parser, label, 2, nullptr);
    copy = game::field<void*>(parser, 0x30);
    copied_word = game::array_item(game::field<void*>(copy, 0x38), 0);
    assert(text_value(game::field<void*>(copied_word, 0x20)) == u"Gyárados helped out by using Surf!");
    pointer(label, 0x18, make_text(u"97-msg_rock_02"));
    TraversalMessage::Callback(parser, label, 2, nullptr);
    copy = game::field<void*>(parser, 0x30);
    copied_word = game::array_item(game::field<void*>(copy, 0x38), 0);
    assert(text_value(game::field<void*>(copied_word, 0x20)) == u"Gyárados helped out by using Rock Climb!");
    node(user).rock_climb = false;
    TraversalMessage::Callback(parser, label, 2, nullptr);
    assert(game::field<void*>(parser, 0x30) == label && handles.empty());
    pointer(label, 0x18, make_text(u"97-msg_kairiki_04"));
    TraversalMessage::Callback(parser, label, 2, nullptr);
    assert(game::field<void*>(parser, 0x30) == label && handles.empty());
    std::cout << "Surf/Waterfall/Rock Climb lifecycle: selection, loading, visibility, cancellation, fallback, teardown, live configuration, previews and dialogue passed\n";
}
