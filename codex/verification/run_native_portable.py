#!/usr/bin/env python3
"""Run original assertions via a portable shim, plus owned offscreen API checks.

Does not launch the native app, create windows, send OS input, or inspect screens.
Original XCTest test bodies/assertions remain unchanged. Imports and #filePath
fixture lookup are adapted only in temporary copies. This is NOT swift test.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EVIDENCE = ROOT / 'codex/evidence/native-portable'


def run(command, name, env=None):
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env, timeout=180)
    (EVIDENCE / f'{name}.log').write_text(result.stdout)
    print(result.stdout, end='')  # Complete compiler diagnostics, never tail only.
    result.check_returncode()
    return result.stdout


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    summary = {'method': 'portable assertion shim; not official XCTest',
               'screen_capture': False, 'os_input': False, 'windows_created': False}
    with tempfile.TemporaryDirectory(prefix='native-verification-', dir=HERE) as temp:
        work = Path(temp)
        tests = []
        inventory = {}
        for original in sorted((ROOT / 'native/macos/Tests').glob('*Tests.swift')):
            text = original.read_text()
            methods = re.findall(r'^    func (test\w+)\(\)', text, flags=re.M)
            cls = re.search(r'final class (\w+): XCTestCase', text)[1]
            inventory[cls] = methods
            text = text.replace('import XCTest\n', 'import Foundation\n').replace('@testable import BigFishCore\n', '')
            text = text.replace('#filePath', json.dumps(str(original)))
            target = work / original.name
            target.write_text(text)
            tests.append(str(target))
        runner = ['import Foundation', 'var methodCount = 0']
        for cls, methods in inventory.items():
            for method in methods:
                runner.extend(['do {', f'let test = {cls}()', 'try test.setUpWithError()',
                               f'test.{method}()', 'try test.tearDownWithError()',
                               'methodCount += 1', f'print("PASS {cls}.{method}")',
                               '} catch { assertionFailures += 1; print("ERROR \\(error)") }'])
        runner.extend(['print("PORTABLE_RESULT methods=\\(methodCount) assertions=\\(assertionCount) failures=\\(assertionFailures)")',
                       'exit(assertionFailures == 0 ? 0 : 1)'])
        main_swift = work / 'main.swift'
        main_swift.write_text('\n'.join(runner) + '\n')
        pure_sources = [ROOT / 'native/macos/Sources' / name for name in
                        ['AnimationModel.swift', 'AnimationRules.swift', 'LayoutStore.swift', 'PetGeometry.swift']]
        binary = work / 'portable-tests'
        compile_command = ['/usr/bin/swiftc', '-swift-version', '5', *map(str, pure_sources),
                           str(HERE / 'PortableAssertions.swift'), *tests,
                           str(main_swift), '-o', str(binary)]
        run(compile_command, 'original-core-build')
        output = run([str(binary)], 'original-core-tests')
        summary['original_suites'] = inventory
        summary['original_result'] = re.search(r'PORTABLE_RESULT (.*)', output)[1]
        summary['original_sources_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                               for p in pure_sources}
        summary['original_test_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                            for p in (ROOT / 'native/macos/Tests').glob('*Tests.swift')}
        for variant, directory in [('original', ROOT / 'native/macos/Sources'),
                                   ('adapted', ROOT / 'codex/dist/native')]:
            main_swift.write_text((HERE / 'NativeControllerChecks.swift').read_text())
            sources = sorted(p for p in directory.glob('*.swift') if p.name != 'main.swift')
            source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sources}
            summary[f'{variant}_controller_sources_sha256'] = source_hashes
            command = ['/usr/bin/swiftc', '-swift-version', '5', *map(str, sources),
                       str(HERE / 'PortableAssertions.swift'), str(main_swift),
                       '-framework', 'AppKit', '-framework', 'UserNotifications',
                       '-framework', 'ApplicationServices', '-framework', 'QuartzCore',
                       '-o', str(binary)]
            run(command, f'{variant}-controller-build')
            env = {k: v for k, v in os.environ.items() if not k.startswith('DSH_DAFEIYU_')}
            output = run([str(binary), '--headless', str(ROOT), str(EVIDENCE), variant],
                         f'{variant}-controller-tests', env=env)
            assert source_hashes == {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sources}, 'Sources changed during verification'
            summary[f'{variant}_controller_result'] = re.search(r'CONTROLLER_RESULT (.*)', output)[1]
        comparison = []
        for original in sorted(EVIDENCE.glob('original-*.rgba')):
            adapted = original.with_name(original.name.replace('original-', 'adapted-', 1))
            left, right = original.read_bytes(), adapted.read_bytes()
            mismatch = sum(a != b for a, b in zip(left, right)) + abs(len(left) - len(right))
            comparison.append({'case': original.stem.removeprefix('original-'),
                               'bytes': len(left), 'differing_channels': mismatch,
                               'sha256': hashlib.sha256(left).hexdigest()})
        summary['offscreen_comparisons'] = comparison
        summary['manifest_sha256'] = hashlib.sha256((ROOT / 'assets/pet-manifest.json').read_bytes()).hexdigest()
        summary['limitations'] = [
            'Portable runner is not official XCTest; no XCTest discovery or runtime exercised.',
            'Clicks are direct controller API calls, not OS mouse dispatch.',
            'Display rectangles are geometry fixtures, not actual displays.',
            'Bitmap comparisons cover the pet renderer, not status-card text or whole windows.',
            'No actual multi-display drag, fullscreen/Spaces, click-through, menus or permission UI acceptance.'
        ]
        for raw in EVIDENCE.glob('*.rgba'):
            raw.unlink()  # PNG evidence and pixel-data SHA-256 remain; avoid redundant large files.
        (EVIDENCE / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        assert comparison and all(row['differing_channels'] == 0 for row in comparison)
        print(f'OFFSCREEN_RESULT comparisons={len(comparison)} differing_channels=0')


if __name__ == '__main__':
    main()
