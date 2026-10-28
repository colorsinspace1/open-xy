// Stock sample dispatch for every registered SDK sample engine. A matching
// engine number is not enough: the machine's registration must still be ours.
// The stubs in sample_hooks.s call these from inside stock functions.
#include "sample_machines.hpp"

using opxy::u32;
using opxy::platform::SampleMachine;

extern "C" {
u32 sdk_sample_note_route(u32) __asm__("sdk_sample_note_route");
u32 sdk_sample_alias(u32) __asm__("sdk_sample_alias");
}

const SampleMachine* sdk_sample_machine(u32 engine) {
    for (u32 i = 0; i < sdk_sample_machine_count; ++i) {
        const SampleMachine& m = sdk_sample_machines[i];
        if (m.engine() == engine) return m.ready() == 1 ? &m : nullptr;
    }
    return nullptr;
}

// Note-region hook, decoded by extensions_sample_note_region (sample_hooks.s).
// Single-sample machines borrow the sampler's payload and region zero.
// Other machines keep nearest-region lookup or canonical drum pads.
enum NoteRoute : u32 { kStockRoute = 0, kOwnedNearest = 1, kOwnedDrumPads = 2, kOwnedSampler = 3 };
u32 sdk_sample_note_route(u32 engine) {
    const SampleMachine* m = sdk_sample_machine(engine);
    return !m ? kStockRoute : m->single_sample ? kOwnedSampler : m->page == 7 ? kOwnedDrumPads : kOwnedNearest;
}

// Stock's sample predicates know only stock engine IDs. Owned SDK engines
// use the same policy for GUI assignment/recording and note playback.
// The track keeps the real engine.
u32 sdk_sample_alias(u32 engine) {
    const SampleMachine* m = sdk_sample_machine(engine);
    return m ? (m->single_sample ? 2 : 30) : engine;
}
