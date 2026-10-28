# Measure CPU cost on your OP-XY

New or changed `draft` and `published` catalog entries must include a hardware
`cpu` measurement for their pinned machine commit. This applies to synths,
sample engines and effects. Unchanged older entries can remain without one
until their next update. A maintainer can run a batch for contributors who do
not have hardware; contributors can also follow this procedure themselves.
The [host estimate](api.md#cpu) is useful during development but cannot fill
this field. CI validates the record and revision; it cannot independently
attest that a contributor ran the hardware test.

## Build and install

Use the SDK's `staging` branch and commit your machine changes before building.
Follow [building firmware](build.md) to install the pinned tools and obtain your
own stock OS. Keep firmware and packages outside every checkout. In the commands
below, `<private>` is that external folder and `<machine>` is your machine folder.

```sh
python -m pip install python-rtmidi
python sdk.py build --machine <machine> --profiling on --stock-os <private>/stock-1.2.1/os.ldr --out <private>/cpu-build-001
```

Repeat `--machine` or use `--collection` to build a batch. Keep the package:
its manifest and compile report identify the firmware and expected test order.
Install its `candidate/` files using [the installation steps](build.md#5-install),
write the OS to the boot partition, and power-cycle. The bootloader is unchanged.
Website builds disable the required per-voice counters; use the SDK build above.

Boot to the normal instrument screen, with USB connected. MTP mode does not
provide the MIDI endpoint. Save your project and stop playback: this is an
active diagnostic that plays its own notes and changes temporary instrument
settings. Close applications holding the XY's MIDI ports and leave USB audio off.
The collector needs exactly one OP-XY MIDI input/output pair. It uses USB MIDI,
not a serial/CDC port. No additional dev-menu toggle is needed after booting
the installed development image normally.

## Collect three runs

Run these sequentially. Each output directory must be new.

```sh
python sdk.py profile benchmark --package <private>/cpu-build-001 --installed --greet --out <private>/cpu-run-001
python sdk.py profile benchmark --package <private>/cpu-build-001 --installed --greet --out <private>/cpu-run-002
python sdk.py profile benchmark --package <private>/cpu-build-001 --installed --greet --out <private>/cpu-run-003
```

`--installed` confirms that this exact package is on the device and your work is
saved. Metadata identifies normal OS 1.2.1 but does not attest the installed image
hash. The collector checks CRCs, endpoint, packet size, and the complete ordered
report count before assigning results to machines. A missing or failed
registration cannot silently shift the reported names. Do not operate the
instrument while a run is active. Each command waits up to 60 seconds for data.

Each run saves `capture.json`, raw `traffic.jsonl`, and a readout. Keep these
private: device metadata can contain a serial number. The command installs no
firmware and never reboots the device. Restart the instrument after testing
before resuming normal work; do not save the diagnostic's temporary settings.

For connection diagnosis, `python sdk.py profile probe --greet --out <fresh-folder>`
requests metadata without running the benchmark. `profile selftest` exercises
the protocol codec without opening a device. An inactive/failed workload, missing
reports, or disabled profiling is a failed measurement, never a zero-cost machine.

## Add the catalog field

The following is offline; `--machine` here takes the machine ID, not its
folder. It verifies that the clean, committed machine source still matches the
measured package.

```sh
python sdk.py profile report --package <private>/cpu-build-001 --machine mymachine --capture <private>/cpu-run-001/capture.json --capture <private>/cpu-run-002/capture.json --capture <private>/cpu-run-003/capture.json --out <private>/cpu-report-001
```

Copy the `cpu` member from `catalog-cpu.json` into your machine's entry in
`catalog/machines.json`. To link evidence as well, publish the generated
`report.md` (an issue, PR comment or file in your repository) and pass its URL
with `--report-url`; if you only learn a comment's permalink after posting,
rerun the offline report command into a new directory with it. No new device
run is needed. The report omits serial numbers and local paths. Share the raw
captures privately with a maintainer if needed; never publish firmware or
firmware-containing packages.

| `cpu` field | Meaning |
| --- | --- |
| `benchmark` | Versioned workload from the table below; must match the machine kind |
| `commit` | Full machine source SHA, equal to the catalog entry's `commit` (or an earlier release's, when a maintainer approves carrying it over) |
| `firmware_sha256` | Exact tested candidate OS image |
| `runs` | 3 to 100 independent, complete captures of the same build and collector |
| `block_percent` | Median of the per-run mean costs, as a percentage of the stock 580,352-cycle block budget |
| `report` | Optional: public HTTPS evidence URL containing the generated readout |

Updating a machine's commit requires a new measurement, unless a catalog
maintainer approves keeping the previous one ([catalog updates](catalog.md#submit-a-machine)).
CI rejects stale results, host estimates, non-finite/zero/saturated values and
missing records on changed submissions. Retiring an entry does not require a new run. Validate your submission:

```sh
python sdk.py catalog check --base origin/staging
```

## What is measured

All workloads run on the Blackfin handling the diagnostic USB-MIDI command.
They are synthetic measurements on real hardware, not passive measurements of
the audio core during normal project playback. Every block is 64 samples.

| Machine kind / benchmark | Scope and fixed workload |
| --- | --- |
| Synth / `opxy-synth-c8-v1` | Stock whole-voice timer, including oscillator and filter. Stock diagnostic plays note 60 at velocity 127 for 1,000 blocks and releases for 500. Controls 0-3 are set to midpoint. This is not a sweep of models or additional controls. |
| Effect / `opxy-effect-callback-v1` | One stereo `process` callback at declared defaults for 1,500 blocks. Deterministic triangle/impulse input, separate initialized state, zeroed private scratch buffer when declared, 120 BPM transport. Includes the wet algorithm, not the stock send/mix path. |
| Sample / `opxy-sample-callback-v1` | One `render_sample` callback at declared defaults for 1,500 blocks. A generated two-second, mono 44.1 kHz PCM triangle/impulse sample, full region, unity level, forward playback, C4 pitch, 120 BPM, no transpose; note restarts every 500 blocks. Declared sample analysis and assignment run before timing. Output uses the machine's mono/stereo contract. |

Sample and effect tests allocate their own buffers during setup, outside audio
callbacks, and free them afterward. They do not borrow a project's assigned sample,
live voice or send scratch buffer. Failed allocation/preparation or an entirely
silent fixture yields an invalid measurement. Their stopwatch includes counter-call
overhead and may include interrupt time; the stock synth runner masks interrupts
while rendering. Do not compare different scopes as though they include the same work.

100% is the stock diagnostic's normalization budget, not total device utilization.
The number is neither a worst-case bound nor a maximum-polyphony prediction.
Graphics, project scheduling, disk/USB I/O and sample preparation are excluded.
Check demanding settings, control motion, many simultaneous voices, feedback/tails
and normal playback separately. A successful benchmark is not full hardware acceptance.

## Agents and maintainers

`sdk.py test`, `check`, `build` and catalog CI never contact a device. Hardware
profiling is an explicit task: confirm the user wants the device test, prepare
and verify a local build, install only when instructed, then wait for the user to
flash/reboot before collecting. Do not infer installed firmware from a package
path or turn host timings into hardware claims. The same batch captures can
produce one offline report per included machine.
