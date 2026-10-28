// SDK ABI fixture: drive the generated synth voice adapter as stock does, with
// a machine of two voices and every stock voice index 0..255.
#include "voice.cpp"
#include <cstring>

int destroyed[257];
// Every encoder shows an alternate. Record names must still identify raw slots.
opxy::u32 sdk_synth_title_slot(opxy::u32, opxy::u32 index) { return index + 4; }

namespace {
typedef int (*Method)(void*);
typedef int (*Render)(void*, opxy::i32*, const opxy::i32*);
void* handle[256];
int call(unsigned index, unsigned entry) {
    const void* const* table = *static_cast<const void* const* const*>(handle[index]);
    return reinterpret_cast<Method>(const_cast<void*>(table[entry]))(handle[index]);
}
// The owner a voice index renders as, 0 for silence; -1 when output is mixed.
opxy::i32 rendered(unsigned index) {
    const void* const* table = *static_cast<const void* const* const*>(handle[index]);
    opxy::i32 output[64], parameters[8] = {};
    for (opxy::i32& word : output) word = -7;
    reinterpret_cast<Render>(const_cast<void*>(table[2]))(handle[index], output, parameters);
    for (opxy::i32 word : output)
        if (word != output[0]) return -1;
    return output[0];
}
void start(unsigned index) { call(index, 4); }
void end(unsigned index) { call(index, 0); }
}

int main() {
    const char* labels[] = {"shape", "width", "level", "motion", "extra 0", "extra 1", "extra 2", "extra 3"};
    for (unsigned i = 0; i < 8; ++i)
        if (std::strcmp(probe_parameter_name(i), labels[i])) return 11;
    if (*probe_parameter_name(8) || *probe_parameter_name(0xffffffffu)) return 12;
    // Every stock index gets an object; none past the last.
    for (unsigned i = 0; i < 256; ++i)
        if (!(handle[i] = probe_factory(i))) return 1;
    if (probe_factory(256)) return 2;
    // Nothing sounds before a note.
    if (rendered(200) != 0) return 3;
    // Two notes take the two voices.
    start(0); start(1);
    if (rendered(0) != 1 || rendered(1) != 2) return 4;
    // A third note takes the voice of the note that started first, which is
    // destroyed for it and from then on renders silence.
    start(200);
    if (destroyed[1] != 1 || rendered(0) != 0 || rendered(200) != 201 || rendered(1) != 2) return 5;
    // A note that still holds its voice keeps it: no new initialize.
    const unsigned before = voices[0].voice.initialized + voices[1].voice.initialized;
    start(1);
    if (voices[0].voice.initialized + voices[1].voice.initialized != before || rendered(1) != 2) return 6;
    // Ending a note frees its voice for the next one without taking another's.
    end(200);
    if (destroyed[201] != 1 || rendered(200) != 0) return 7;
    start(7);
    if (rendered(7) != 8 || rendered(1) != 2 || destroyed[2] != 0) return 8;
    // Ending a note whose voice was taken destroys nothing again.
    end(0);
    if (destroyed[1] != 1) return 9;
    // A long run of notes on every index never fails.
    for (unsigned n = 0; n < 2000; ++n) {
        start(n * 37 % 256);
        if (rendered(n * 37 % 256) != static_cast<opxy::i32>(n * 37 % 256 + 1)) return 10;
    }
    return 0;
}
