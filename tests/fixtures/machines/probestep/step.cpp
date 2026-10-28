#include <opxy/step.hpp>

namespace probestep {
// Settings 0..8 move the note -12, -3..+3 or +12 semitones; setting 9 sets velocity 13.
void apply(opxy::StepNote& note, opxy::u32 setting) {
    static const opxy::i32 kIntervals[8] = {-12, -1, -2, -3, 0, 1, 2, 3};
    if (setting == 8) {
        note.pitch += 12;
    } else if (setting == 9) {
        note.velocity = 13;
    } else {
        note.pitch += kIntervals[setting];
    }
}
}
