#!/usr/bin/env python3
"""Compare every manifest frame and a finite complete static PetView matrix.

Uses private AppKit bitmap contexts. Never launches app/windows or OS controls.
Only the host-branded default detail string is normalized in TEMPORARY sources.
Original assets and source trees are read-only. No official XCTest or live UI claim.
"""
import hashlib
import gzip
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / 'codex/evidence/full-visual'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, label, env=None):
    with (OUT / f'{label}.log').open('w') as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        for line in process.stdout:
            print(line, end='', flush=True)
            log.write(line); log.flush()
        if process.wait():
            raise RuntimeError(f'{label} failed; full diagnostics in {log.name}')


def main():
    start = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'rerender.json').unlink(missing_ok=True)
    manifest = json.loads((ROOT / 'assets/pet-manifest.json').read_text())
    tracked = sorted(set([ROOT / 'assets/pet-manifest.json'] +
                         [p for folder in ['native/macos/Sources', 'codex/dist/native'] for p in (ROOT / folder).glob('*.swift')] +
                         [ROOT / 'assets/pet' / frame for clip in manifest['clips'].values() for frame in clip['frames']]))
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in tracked}
    summary = {'method': 'real PetView.draw into owned flipped AppKit bitmap contexts; SHA-256 of all RGBA channels',
               'windows_created': False, 'screen_capture': False, 'os_input': False,
               'platform': platform.platform(), 'sources_and_assets_sha256': hashes,
               'normalization': {'original': 'DSH · 等待下一次任务 → HOST · 等待下一次任务',
                                 'adapted': 'Codex · 等待下一次任务 → HOST · 等待下一次任务',
                                 'scope': 'Only this literal in temporary PetController.swift copies (initial detail and fallback card); original source trees untouched. Explicit protocol message/detail, tasks, openLabel=Host, footer identical otherwise.'},
               'static_test_instrumentation': 'Temporary PetController copies expose verificationSettleFade() to set private fadeFromFrame=nil immediately before every draw. Protocol state updates remain real; crossfade timing is explicitly excluded. All bitmaps must contain nonzero alpha.',
               'clips': {name: len(clip['frames']) for name, clip in manifest['clips'].items()},
               'sizes_percent': [55, 80, 100], 'bubble_scales_percent': [80, 100, 120],
               'states': sorted(manifest['stateMap']),
               'activities': ['none'] + sorted(manifest['workingActivityMap']),
               'bubble_modes': ['always', 'hidden', 'custom'],
               'activity_levels': ['quiet', 'normal', 'lively'], 'reduced_motion': [False, True],
               'profiles': ['status', 'long', 'empty-detail', 'overlay', 'task1', 'task2', 'task3', 'task4', 'footer', 'task-footer', 'no-card', 'fallback-footer'],
               'limitations': ['Finite static matrix, not arbitrary strings/Unicode/fonts/settings combinations or infinite time sequences.',
                               'Every frame checked at all three common sizes; card matrix uses frame zero for each state/activity, not every frame crossed with every card.',
                               'System fonts and rasterization are those of this machine at 1 bitmap pixel per point; not other OS/font versions or Retina/backing-scale acceptance.',
                               'No live windows, OS hit testing, screen capture, Spaces/fullscreen, menus, notifications, drag, or actual display acceptance.',
                               'Crossfades and wall-clock animation/timer transitions are not sampled by this static renderer.',
                               'Host branding intentionally differs and is explicitly normalized only for static layout parity. Menu/window/notification branding not rendered.']}
    env = {k: v for k, v in os.environ.items() if not k.startswith('DSH_DAFEIYU_')}
    with tempfile.TemporaryDirectory(prefix='full-visual-', dir=HERE) as tmp:
        tmp = Path(tmp)
        runner = tmp / 'main.swift'; runner.write_text((HERE / 'FullVisualChecks.swift').read_text())
        binaries = {}
        for variant, directory, host in [('original', ROOT / 'native/macos/Sources', 'DSH'), ('adapted', ROOT / 'codex/dist/native', 'Codex')]:
            dest = tmp / variant; dest.mkdir()
            sources = []
            normalizations = 0
            for path in sorted(directory.glob('*.swift')):
                if path.name == 'main.swift': continue
                text = path.read_text()
                if path.name == 'PetController.swift':
                    normalizations += text.count(f'{host} · 等待下一次任务')
                    text = text.replace(f'{host} · 等待下一次任务', 'HOST · 等待下一次任务')
                    hook = '    func verificationSettleFade() { fadeFromFrame = nil }\n\n'
                    anchor = '    static func clampedScale(_ value: Double) -> Double {'
                    assert text.count(anchor) == 1
                    text = text.replace(anchor, hook + anchor)
                target = dest / path.name; target.write_text(text); sources.append(target)
            assert normalizations == 2, (variant, normalizations)
            summary[f'{variant}_rendered_sources_sha256'] = {p.name: sha(p) for p in sources}
            binary = dest / 'verify'; binaries[variant] = binary
            run(['/usr/bin/swiftc', '-O', '-swift-version', '5', *map(str, sources), str(runner),
                 '-framework', 'AppKit', '-framework', 'UserNotifications', '-framework', 'ApplicationServices',
                 '-framework', 'QuartzCore', '-o', str(binary)], f'{variant}-build')
            run([str(binary), '--headless', str(ROOT), str(OUT), variant], f'{variant}-render', env)
        records = {}
        for variant in binaries:
            rows = [json.loads(line) for line in (OUT / f'{variant}-cases.jsonl').read_text().splitlines()]
            records[variant] = {r['id']: r for r in rows}
            assert len(rows) == len(records[variant]), 'Duplicate case identifiers'
        assert records['original'].keys() == records['adapted'].keys(), 'Case inventory differs'
        failures = []
        for key, left in records['original'].items():
            right = records['adapted'][key]
            if left != right:
                failures.append({'id': key, 'original': left, 'adapted': right})
        if failures:
            (OUT / 'rerender.json').write_text(json.dumps([row['id'] for row in failures]))
            for variant, binary in binaries.items():
                # Preserve complete first-pass records before mismatch-only re-render.
                full = OUT / f'{variant}-cases.jsonl'
                full.rename(OUT / f'{variant}-all-cases.jsonl')
                run([str(binary), '--headless', str(ROOT), str(OUT), variant], f'{variant}-mismatches', env)
                full.unlink(); (OUT / f'{variant}-all-cases.jsonl').rename(full)
            for row in failures:
                left = (OUT / f"original-{row['id']}.rgba").read_bytes()
                right = (OUT / f"adapted-{row['id']}.rgba").read_bytes()
                row['differing_channels'] = sum(a != b for a, b in zip(left, right)) + abs(len(left) - len(right))
            for path in OUT.glob('*.rgba'): path.unlink()
            (OUT / 'rerender.json').unlink()
        (OUT / 'failures.json').write_text(json.dumps(failures, indent=2) + '\n')
    assert hashes == {str(p.relative_to(ROOT)): sha(p) for p in tracked}, 'Source/asset mutation during verification'
    # Contact sheets, then remove redundant individual representative PNGs.
    from PIL import Image, ImageDraw
    for group, prefix in [('frames', 'frame-'), ('cards', 'card-')]:
        for variant in ['original', 'adapted']:
            paths = sorted(OUT.glob(f'{variant}-{prefix}*.png'))
            paths = [p for p in paths if not any(p.name == f"{variant}-{r['id']}.png" for r in failures)]
            if not paths: continue
            cols, tw, th = 4, 310, 360
            sheet = Image.new('RGB', (cols * tw, ((len(paths) + cols - 1) // cols) * th), '#e6e6e6')
            draw = ImageDraw.Draw(sheet)
            for index, path in enumerate(paths):
                im = Image.open(path).convert('RGBA'); im.thumbnail((tw - 12, th - 60))
                x, y = (index % cols) * tw + 6, (index // cols) * th
                sheet.paste(im, (x, y + 55), im)
                label = path.stem.removeprefix(f'{variant}-')
                draw.text((x, y + 3), label[:42] + '\n' + label[42:84], fill='black')
            sheet.save(OUT / f'{variant}-{group}-contact-sheet.jpg', quality=88)
            for path in paths: path.unlink()
    groups = {}
    for row in records['original'].values(): groups[row['group']] = groups.get(row['group'], 0) + 1
    expected_frames = sum(summary['clips'].values()) * 3
    expected_cards = 7 * 6 * 3 * 3 * 3 * 3 * 2 * 12
    assert groups == {'frames': expected_frames, 'cards': expected_cards, 'visibility': 14}, groups
    summary.update({'comparisons_by_group': groups, 'total_comparisons': sum(groups.values()),
                    'actual_renders_both_variants': sum(groups.values()) * 2,
                    'mismatch_count': len(failures), 'elapsed_seconds': round(time.monotonic() - start, 3),
                    'verifier_sha256': {p.name: sha(p) for p in [HERE / 'FullVisualChecks.swift', Path(__file__)]}})
    for variant in records:
        path = OUT / f'{variant}-cases.jsonl'
        compressed = path.with_suffix('.jsonl.gz')
        compressed.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
        path.unlink()
    summary['case_records_sha256'] = {v: sha(OUT / f'{v}-cases.jsonl.gz') for v in records}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: summary[k] for k in ['comparisons_by_group', 'total_comparisons', 'actual_renders_both_variants', 'mismatch_count', 'elapsed_seconds']}, indent=2))
    if failures: raise SystemExit(1)


if __name__ == '__main__': main()
