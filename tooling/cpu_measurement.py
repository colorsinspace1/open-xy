"""Revision-bound hardware measurements required for changed catalog submissions."""
import math
import re

from .formats import require

BENCHMARKS = {'synth': 'opxy-synth-c8-v1', 'effect': 'opxy-effect-callback-v1',
              'sample': 'opxy-sample-callback-v1'}
FIELDS = {'benchmark', 'commit', 'firmware_sha256', 'runs', 'block_percent'}
# An optional public evidence URL, never a local path or a URL with credentials.
REPORT_URL = r'https://[A-Za-z0-9.-]+(?::[0-9]+)?/[^\s<>"\\]*'


def validate(value, kind, commit=None):
    """A measurement's fields; with a commit, also that it measured that commit."""
    require(isinstance(value, dict) and set(value) - {'report'} == FIELDS, 'cpu: unexpected measurement fields')
    require(kind in BENCHMARKS and value['benchmark'] == BENCHMARKS[kind], 'cpu: benchmark must match the machine kind')
    require(isinstance(value['commit'], str) and re.fullmatch(r'[0-9a-f]{40}', value['commit']),
            'cpu: commit is the full SHA of the measured machine source')
    require(commit is None or value['commit'] == commit, 'cpu: measurement must match the catalog commit')
    require(isinstance(value['firmware_sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', value['firmware_sha256']),
            'cpu: firmware_sha256 must identify the measured build')
    require(type(value['runs']) is int and 3 <= value['runs'] <= 100, 'cpu: use 3 to 100 independent runs')
    for field in ('block_percent',):
        number = value[field]
        require(type(number) in (int, float) and math.isfinite(number) and 0 < number < 100,
                f'cpu: {field} must be an unsaturated, positive percentage of the stock block budget')
    if 'report' in value:
        require(isinstance(value['report'], str) and len(value['report']) <= 2048 and
                re.fullmatch(REPORT_URL, value['report']), 'cpu: report must be a public HTTPS evidence URL')
    return value
