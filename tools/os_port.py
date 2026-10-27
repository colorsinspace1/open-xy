"""Locate a firmware profile's reviewed edits and stock addresses in another OS release.

Porting aid for a new stock OS (for example OP-XY 1.2.1), run against two
private stock images. It never writes firmware. For every profile edit it finds
the same code in the target image by its surrounding bytes, tolerant of the
relative branches and addresses that change when code moves, and for a hook
that replaces a call it checks the call reaches the same stock function. For
every stock address the platform layer and tooling name, it finds the same
bytes in the target. The report says which map cleanly and which need review.

    python tools/os_port.py --source <stock-1.2.0>/os.ldr --target <stock-1.2.1>/os.ldr --out local/port-1.2.1
"""
import argparse
import json
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tooling.firmware import absolute_target, decode_branch  # noqa: E402
from tooling.formats import ldr, require  # noqa: E402

# Bytes compared either side of an edit, and how far from its old place to look.
CONTEXT, WINDOW = 48, 40000
# Agreement of the context and its lead over the next best place, for a confident match.
AGREE, MARGIN = 0.8, 0.2
# Where the platform layer and tooling name stock addresses.
SOURCES = ('sdk/platform/opxy-1.2.0', 'tooling/stock_tables.py', 'tooling/firmware.py', 'tooling/native.py')
ADDRESS = re.compile(r'0x(?:8[4cdf]|08|11[89ab])[0-9a-fA-F]{5,6}\b')


class Image:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        self.bytes = np.frombuffer(self.data, np.uint8)
        self.blocks = [b for b in ldr(self.data) if not b['fill'] and b['count']]

    def offset(self, address):
        for b in self.blocks:
            if b['target'] <= address < b['target'] + b['count']:
                return b['offset'] + 16 + address - b['target']
        return None

    def address(self, offset):
        for b in self.blocks:
            start = b['offset'] + 16
            if start <= offset < start + b['count']:
                return b['target'] + offset - start
        return None


def locate(source, target, offset, length, context=CONTEXT, window=WINDOW, expected=None):
    """(target offset, agreement, margin) of the source bytes [offset, offset+length) with context.
    Among equally good places (repeated code), the one nearest `expected` wins, its margin
    then measured against places that agree less."""
    low = max(0, offset - context)
    pattern = source.bytes[low: offset + length + context]
    size = len(pattern)
    start = max(0, low - window)
    stop = min(len(target.bytes) - size, low + window)
    if stop <= start:
        return None, 0.0, 0.0
    views = np.lib.stride_tricks.sliding_window_view(target.bytes[start: stop + size], size)
    score = (views == pattern).sum(axis=1)
    best = int(score.argmax())
    ties = np.flatnonzero(score == score[best])
    if expected is not None and len(ties) > 1:
        best = int(ties[np.abs(start + ties + (offset - low) - expected).argmin()])
        others = np.where(score == score[best], 0, score)
    else:
        others = score.copy()
    others[max(0, best - 4): best + 5] = 0
    return start + best + (offset - low), float(score[best]) / size, float(score[best] - others.max()) / size


def call_target(site, data):
    """The stock function a replaced instruction calls or jumps to, or None."""
    try:
        if len(data) == 8:
            return absolute_target(data)
        return decode_branch(site, data[:4])[0]
    except ValueError:
        return None


def same_function(source, target, old, new, length=64):
    """Agreement of the first bytes of a stock function and its candidate in the target."""
    a, b = source.offset(old), target.offset(new)
    if a is None or b is None:
        return 0.0
    return float((source.bytes[a: a + length] == target.bytes[b: b + length]).mean())


def port_edits(source, target, profile):
    rows = []
    for edit in profile['patches']:
        offset, length = int(edit['file_offset'], 16), edit['length']
        before = bytes.fromhex(edit['before'])
        require(source.data[offset: offset + length] == before, 'Source image is not this profile\'s stock OS')
        found, agree, margin = locate(source, target, offset, length)
        row = dict(name=edit.get('name') or edit.get('symbol'), kind=edit['kind'], address=edit['address'],
                   agree=round(agree, 3), margin=round(margin, 3))
        if found is None or agree < AGREE or margin < MARGIN:
            rows.append(dict(row, status='review', reason='no confident match'))
            continue
        new_before = target.data[found: found + length]
        row.update(target_address=hex(target.address(found)), target_offset=hex(found), target_before=new_before.hex(),
                   delta=found - offset)
        if new_before == before:
            rows.append(dict(row, status='verified', reason='identical bytes'))
            continue
        old = call_target(int(edit['address'], 16), before) if edit['kind'] == 'hook' else None
        new = call_target(target.address(found), new_before) if old is not None else None
        if old is not None and new is not None:
            similar = same_function(source, target, old, new)
            status = 'verified' if similar >= 0.7 else 'review'
            rows.append(dict(row, status=status, reason=f'calls {hex(old)} -> {hex(new)} ({similar:.0%} alike)'))
        else:
            # Found in place, but the replaced instructions themselves changed
            # (an address load, a moved table or reworked code): read them.
            rows.append(dict(row, status='located', reason=f'{edit["kind"]} bytes differ at the matching place'))
    return rows


def constant_loads(image):
    """{constant: [file offset]} and {file offset: constant} of 32-bit constants in Blackfin+
    64-bit instructions (0xD8xx-0xDBxx: a register load or an absolute memory access, the
    high then low half-word of the address following the opcode), which is how stock code
    addresses its data."""
    by_value, by_offset = {}, {}
    for block in image.blocks:
        start, count = block['offset'] + 16, block['count'] & ~1
        if block['target'] & 1 or count < 8:
            continue
        words = np.frombuffer(image.data[start: start + count], '<u2')
        for i in np.flatnonzero((words[:-3] & 0xfc00) == 0xd800).tolist():
            constant, at = int(words[i + 1]) << 16 | int(words[i + 2]), start + 2 * i
            by_value.setdefault(constant, []).append(at)
            by_offset[at] = constant
        # Calls reach stock functions: an absolute call (0xDE00, high, low, 0) or a
        # PC-relative CALL (0xE3xx); their targets are constants of the same kind.
        for i in np.flatnonzero(words[:-3] == 0xde00).tolist():
            if words[i + 3] == 0:
                constant, at = int(words[i + 1]) << 16 | int(words[i + 2]), start + 2 * i
                by_value.setdefault(constant, []).append(at)
                by_offset[at] = constant
        for i in np.flatnonzero((words[:-1] & 0xff00) == 0xe300).tolist():
            at = start + 2 * i
            constant = call_target(block['target'] + 2 * i, image.data[at: at + 4])
            if constant is not None:
                by_value.setdefault(constant, []).append(at)
                by_offset[at] = constant
    return by_value, by_offset


def port_addresses(source, target, anchors, edits=(), own=()):
    """anchors: (source file offset, file offset shift) of verified matches, to place repeated code;
    edits: the edit rows, whose sites tooling also names; own: (start, end, shift) of SDK-owned
    memory (the module reservation), which moves with the stock heap rather than by content."""
    found = {}
    for name in SOURCES:
        path = ROOT / name
        for file in ([path] if path.is_file() else sorted(path.rglob('*'))):
            if file.is_file():
                for match in ADDRESS.finditer(file.read_text(encoding='utf-8', errors='replace')):
                    found.setdefault(int(match.group(), 16), set()).add(str(file.relative_to(ROOT).as_posix()))
    shift = lambda offset: min(anchors, key=lambda a: abs(a[0] - offset))[1] if anchors else 0
    source_loads, _ = constant_loads(source)
    _, target_loads = constant_loads(target)
    bases = sorted(source_loads)

    def by_references(address):
        # The code that loads the address, or the struct it lies in (within 1 KiB), found in
        # the target; the constant it loads there, plus the same field offset, by majority.
        import bisect
        i = bisect.bisect_right(bases, address) - 1
        if i < 0 or address - bases[i] > 1024:
            return None, 0
        base = bases[i]
        votes = {}
        for at in source_loads[base][:12]:
            new, agree, margin = locate(source, target, at, 8, context=24, expected=at + shift(at))
            if new is None or agree < AGREE:
                continue
            # The same instruction at the matching place: same opcode, nearest first.
            opcode = source.data[at: at + 2]
            for probe in (new, new - 2, new + 2, new - 4, new + 4):
                if probe in target_loads and target.data[probe: probe + 2] == opcode:
                    value = target_loads[probe] + address - base
                    votes[value] = votes.get(value, 0) + 1
                    break
        if not votes:
            return None, 0
        value = max(votes, key=votes.get)
        return value, votes[value] / sum(votes.values())

    sites = {int(r['address'], 16): r for r in edits if r['status'] in ('verified', 'located')}
    rows = []
    for address in sorted(found):
        row = dict(address=hex(address), files=sorted(found[address]))
        if address in sites:
            rows.append(dict(row, status='mapped', target_address=sites[address]['target_address'], how='edit site'))
            continue
        moved = next((shift for low, high, shift in own if low <= address < high), None)
        if moved is not None:
            rows.append(dict(row, status='mapped', target_address=hex(address + moved), how='SDK reservation'))
            continue
        offset = source.offset(address)
        if offset is not None:
            new, agree, margin = locate(source, target, offset, 16, context=16, expected=offset + shift(offset))
            if new is not None and agree >= AGREE and margin >= MARGIN:
                rows.append(dict(row, status='mapped', target_address=hex(target.address(new)), how='bytes',
                                 agree=round(agree, 3)))
                continue
        value, share = by_references(address)
        if value is not None and share >= 0.75:
            rows.append(dict(row, status='mapped', target_address=hex(value), how='references', agree=round(share, 3)))
        else:
            rows.append(dict(row, status='review',
                             reason='no confident match by bytes or by the code that loads it' +
                                    (f' (references disagree: {share:.0%})' if value is not None else '')))
    return rows


def regions(image):
    """Loaded bytes per memory area, by the address's top byte."""
    totals = {}
    for b in image.blocks:
        key = hex(b['target'] >> 24)
        totals[key] = totals.get(key, 0) + b['count']
    return dict(sorted(totals.items()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--source', required=True, type=Path, help='stock os.ldr the profile was made for')
    parser.add_argument('--target', required=True, type=Path, help='stock os.ldr of the new release')
    parser.add_argument('--profile', default=ROOT / 'profiles/opxy-1.2.0.json', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    require(not args.out.exists(), 'Use a fresh output directory')
    profile = json.loads(args.profile.read_text(encoding='utf-8'))
    source, target = Image(args.source), Image(args.target)
    edits = port_edits(source, target, profile)
    # The module reservation sits below stock code at the top of the shrunk heap; stock code
    # starts where the heap fill ends, so the reservation moves with it.
    fill = lambda image: max((b for b in ldr(image.data) if b['fill']), key=lambda b: b['count'] if b['count'] < 32 << 20 else 0)
    old_fill, new_fill = fill(source), fill(target)
    old_end, new_end = old_fill['target'] + old_fill['count'], new_fill['target'] + new_fill['count']
    own = [(old_end - profile['reserved_bytes'], old_end, new_end - old_end)]
    addresses = port_addresses(source, target, [(int(r['target_offset'], 16) - r['delta'], r['delta']) for r in edits
                                                if r['status'] == 'verified'], edits, own)
    report_layout = dict(heap_fill_base=hex(new_fill['target']), heap_fill_bytes=new_fill['count'],
                         module_base=hex(new_end - profile['reserved_bytes']), code_start=hex(new_end))
    report = dict(source_bytes=len(source.data), target_bytes=len(target.data), target_layout=report_layout,
                  source_regions=regions(source), target_regions=regions(target), edits=edits, addresses=addresses)
    args.out.mkdir(parents=True)
    (args.out / 'report.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    count = lambda rows, status: sum(r['status'] == status for r in rows)
    lines = [f'Edits: {count(edits, "verified")} verified, {count(edits, "located")} located with changed bytes, '
             f'{count(edits, "review")} to review, of {len(edits)}.',
             f'Stock addresses: {count(addresses, "mapped")} mapped, {count(addresses, "review")} to review, '
             f'of {len(addresses)}.']
    for status in ('review', 'located'):
        lines += ['', f'Edits, {status}:'] + [f'  {r["address"]} {r["kind"]:7} {r["name"]}: {r["reason"]}'
                                               for r in edits if r['status'] == status]
    lines += ['', 'Addresses to review:'] + [f'  {r["address"]} {r["reason"]} ({", ".join(r["files"])})'
                                             for r in addresses if r['status'] == 'review']
    (args.out / 'report.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines[:2]))
    print('Report: ' + str(args.out))


if __name__ == '__main__':
    main()
