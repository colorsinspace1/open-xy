"""Offline aggregation of complete hardware runs, bound to a clean machine revision."""
import json
from pathlib import Path
import statistics

from .benchmark import decode
from .cpu_measurement import validate
from .formats import require, sha


def package_data(package):
    package = Path(package)
    manifest_bytes = (package / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    require(manifest.get('profiling') is True, 'Benchmark requires a profiling-enabled package')
    report_bytes = (package / 'analysis/compile-report.json').read_bytes()
    require(sha(report_bytes) == manifest['files']['analysis/compile-report.json'], 'Compile report hash mismatch')
    require(sha((package / 'candidate/os.ldr').read_bytes()) == manifest['files']['candidate/os.ldr'],
            'Firmware hash mismatch')
    report = json.loads(report_bytes)
    require(report.get('profiling') is True and report.get('benchmark_cases'), 'Missing enabled diagnostic runner')
    identity = dict(manifest_sha256=sha(manifest_bytes), compile_report_sha256=sha(report_bytes),
                    firmware_sha256=manifest['files']['candidate/os.ldr'])
    return manifest, report, identity


def aggregate(captures, expected, identity, name, commit, url):
    require(3 <= len(captures) <= 100, 'Collect 3 to 100 independent runs')
    seen, values, collectors = set(), [], set()
    case = next((c for c in expected if c['name'] == name and c['source'] == 'sdk'), None)
    require(case is not None and 'benchmark' in case, 'Machine is not in this diagnostic package')
    for capture in captures:
        fingerprint = sha(json.dumps(capture, sort_keys=True).encode())
        require(fingerprint not in seen, 'Do not reuse a capture as another run')
        seen.add(fingerprint)
        require(capture.get('mode') == 'benchmark' and capture.get('package') == identity and
                capture.get('expected_cases') == expected, 'Capture belongs to a different build or workload')
        collectors.add(capture.get('collector_sha256'))
        result = next(r for r in decode(capture, expected) if r['machine'] == case)
        metric = result['metrics'][case['metric']]
        require(not result['insufficient_voice_activity'] and 0 < metric['encoded_average'] < 65535,
                'Inactive, failed or saturated workload; do not publish a CPU number')
        values.append(metric['average_budget_percent'])
    require(len(collectors) == 1 and None not in collectors, 'Use the same collector for all runs')
    measurement = dict(benchmark=case['benchmark'], commit=commit, firmware_sha256=identity['firmware_sha256'],
                       runs=len(captures), block_percent=round(statistics.median(values), 6))
    if url is not None:
        measurement['report'] = url
    validate(measurement, case['kind'], commit)
    return measurement, values, case


def create(package, paths, name, url, out):
    from . import native, catalog
    manifest, report, identity = package_data(package)
    _, machines, _ = native.configuration(native.package_collection(package), native.package_layout(package))
    machine = next((m for m in machines if m.id == name), None)
    require(machine is not None, 'Unknown package machine')
    # Publication binds the tested source tree, not an arbitrary user-supplied SHA.
    commit = catalog.git('rev-parse', 'HEAD', cwd=machine.root).strip()
    require(not catalog.git('status', '--porcelain', '--untracked-files=all', '--', '.', cwd=machine.root).strip(),
            'Commit the machine before building and profiling it')
    files = machine.files()
    prefix = 'external/' + name + '/'
    actual = {key: sha(path.read_bytes()) for key, path in files.items()}
    require(actual == {k: v for k, v in report['sources'].items() if k.startswith(prefix)},
            'Machine source differs from the measured build')
    for path in files.values():
        catalog.git('ls-files', '--error-unmatch', '--', str(path.relative_to(machine.root)), cwd=machine.root)
    captures = [json.loads(Path(path).read_text()) for path in paths]
    measurement, values, case = aggregate(captures, report['benchmark_cases'], identity, name, commit, url)
    destination = Path(out)
    require(not destination.exists(), 'Use a fresh report directory')
    destination.mkdir(parents=True)
    (destination / 'catalog-cpu.json').write_text(json.dumps({'cpu': measurement}, indent=2) + '\n')
    scope = 'whole voice, including oscillator/filter' if case['kind'] == 'synth' else 'machine render callback only'
    text = (f"# {name}: hardware CPU measurement\n\n"
            f"Machine commit: `{commit}`. Benchmark: `{case['benchmark']}`. Scope: {scope}.\n\n"
            f"Median of {len(values)} run means: **{measurement['block_percent']:.3f}%** of the stock "
            f"580,352-cycle block budget. Run means: {', '.join(f'{v:.3f}%' for v in values)}.\n\n"
            "This is a synthetic measurement on the USB-MIDI command endpoint, not total device CPU, "
            "maximum polyphony or a worst-case settings sweep. Graphics are excluded. "
            "Callback tests exclude sample preparation, allocation, stock mixing and voice processing; "
            "they include stopwatch-call overhead and may include interrupt time. "
            "See docs/profiling.md for the versioned workloads.\n\n"
            f"Firmware SHA-256: `{identity['firmware_sha256']}`.\n\n"
            f"Compile report SHA-256: `{identity['compile_report_sha256']}`.\n\n"
            "Attribution uses the user-confirmed installed package, expected case order and exact report count; "
            "the device does not attest its firmware hash. Raw captures remain private because they contain device identity.\n")
    (destination / 'report.md').write_text(text, encoding='utf-8')
    return destination
