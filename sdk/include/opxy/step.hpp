#pragma once
#include "types.hpp"

namespace opxy {
// A step component changes each note a sequencer step plays. It takes over one
// of stock's replaceable step components (definition.json and machine.json
// identity "step"); holding shift, a step and that component's white key picks
// it, and the black keys pick one of its ten settings:
//   void apply(opxy::StepNote& note, opxy::u32 setting);   // setting 0..9
// setting is the black key's position, 1..9 then 0 (stock shows its labels in
// that order). apply runs in the sequencer for every note of a step that has
// the component, beside the step's other components: keep it short, with no
// state, allocation or I/O.
//
// pitch is a MIDI note; after every component has run, stock folds it into
// 0..127 by octaves, as the SDK does for values below 0. velocity is the note's
// 0..127 velocity as it reaches this component; a result outside 0..127 is
// clamped, and velocity 0 does not mute the note.
struct StepNote {
    i32 pitch;
    i32 velocity;
};
const unsigned step_settings = 10;
}
