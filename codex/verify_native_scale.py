"""Compile native boundary/persistence checks without the unavailable XCTest SDK."""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify():
    sources = ROOT / 'codex/dist/native'
    with tempfile.TemporaryDirectory(prefix='bigfish-scale-') as tmp:
        tmp = Path(tmp)
        main = tmp / 'main.swift'
        main.write_text('''import AppKit
final class ProtocolIO {
    static let shared = ProtocolIO()
    func write(_ object: [String: Any]) {}
}
func check(_ actual: Double, _ expected: Double) {
    if abs(actual - expected) > 0.000001 {
        fatalError("scale mismatch: \\(actual) != \\(expected)")
    }
}
let path = URL(fileURLWithPath: CommandLine.arguments[1])
for percent in 1...100 {
    let scale = Double(percent) / 100
    check(PetController.clampedScale(scale), scale)
    var layout = PetLayout()
    layout.scale = scale
    layout.save(to: path)
    check(PetLayout.load(from: path).scale, scale)
}
check(PetController.clampedScale(0), 0.01)
check(PetController.clampedScale(1.4), 1)
var legacy = PetLayout()
legacy.scale = 1.25
legacy.save(to: path)
check(PetLayout.load(from: path).scale, 1)
print("Native scale: 1...100 percent clamp/save/load checks passed")
''')
        files = [str(p) for p in sources.glob('*.swift') if p.name != 'main.swift']
        binary = tmp / 'verify-scale'
        subprocess.run(['/usr/bin/swiftc', '-swift-version', '5', *files, str(main),
                        '-framework', 'AppKit', '-framework', 'UserNotifications',
                        '-framework', 'ApplicationServices', '-framework', 'QuartzCore',
                        '-o', str(binary)], check=True)
        subprocess.run([str(binary), str(tmp / 'layout.json')], check=True)


if __name__ == '__main__':
    verify()
