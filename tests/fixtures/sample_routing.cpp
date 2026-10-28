// Exercise the real GUI/key bridge alongside the audio route, with stock calls doubled.
#include <cstdlib>
#include <initializer_list>
extern "C" void host_barrier() {}
#include <drum_controls_stock.cpp>
extern "C" unsigned sdk_sample_note_route(unsigned) __asm__("sdk_sample_note_route");

static void check(bool value) { if (!value) std::abort(); }
static int ownership = 1;
static int ready() { return ownership; }
static const char* symbol(unsigned id) { return reinterpret_cast<const char*>(static_cast<__UINTPTR_TYPE__>(id)); }
const opxy::platform::SampleMachine sdk_sample_machines[] = {
    {symbol(46), 2, ready, 1, nullptr, nullptr, nullptr, nullptr, 0, nullptr, nullptr, nullptr, nullptr},
    {symbol(47), 2, ready, 0, nullptr, nullptr, nullptr, nullptr, 0, nullptr, nullptr, nullptr, nullptr},
    {symbol(48), 7, ready, 0, nullptr, nullptr, nullptr, nullptr, 0, nullptr, nullptr, nullptr, nullptr},
};
const unsigned sdk_sample_machine_count = 3;
static unsigned engine(unsigned track) { return track == 1 ? 47 : track == 2 ? 48 : track == 3 ? 18 : 46; }
static int octave(unsigned track) { check(track == 2); return -1; }
static unsigned pad(unsigned key, int oct) { check(oct == -1); return key % 24; }
opxy::platform::Address opxy::platform::host_stock_address(Address address) {
    if (address == 0x8d58781c) return reinterpret_cast<Address>(&engine);
    if (address == 0x8d58f65c) return reinterpret_cast<Address>(&octave);
    if (address == 0x8d5b8688) return reinterpret_cast<Address>(&pad);
    std::abort();
}
extern "C" unsigned sdk_sample_edit(void*, unsigned, int, unsigned) { std::abort(); }

int main() {
    // Same page, different resolved policies: neither route nor alias infers playback from page 2.
    check(sdk_sample_alias(46) == 2 && sdk_sample_note_route(46) == 3);
    check(sdk_sample_alias(47) == 30 && sdk_sample_note_route(47) == 1);
    check(sdk_sample_alias(48) == 30 && sdk_sample_note_route(48) == 2);
    check(sdk_sample_ui_engine(0) == 2 && sdk_sample_ui_engine(1) == 30 && sdk_sample_ui_engine(2) == 30);
    for (unsigned key = 0; key < 128; ++key) {
        check(sdk_sample_key(0, key) == 0);
        check(sdk_sample_key(1, key) == 0xffffffffu);
        check(sdk_sample_key(2, key) == key % 24 + 53);
        check(sdk_sample_key(3, key) == 0xffffffffu);
    }
    check(sdk_sample_drum_octaves[2] == -1);
    // A send's effect ID can equal a sample engine's number; leave it to stock.
    for (unsigned track : {8u, 14u, 15u}) {
        check(sdk_sample_ui_engine(track) == 46);
        check(sdk_sample_key(track, 60) == 0xffffffffu);
    }
    for (unsigned id : {2u, 18u, 30u, 49u})
        check(sdk_sample_alias(id) == id && sdk_sample_note_route(id) == 0);
    for (int state : {0, 2}) { // absent and conflicting registrations
        ownership = state;
        for (unsigned track = 0; track < 3; ++track) {
            const unsigned id = engine(track);
            check(sdk_sample_alias(id) == id && sdk_sample_note_route(id) == 0);
            check(sdk_sample_ui_engine(track) == id && sdk_sample_key(track, 60) == 0xffffffffu);
        }
    }
}
