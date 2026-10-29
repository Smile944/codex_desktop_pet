import AppKit

// Required transport symbol only. No app process or transport is started.
final class ProtocolIO {
    static let shared = ProtocolIO()
    func write(_ object: [String: Any]) {}
}

let root = URL(fileURLWithPath: CommandLine.arguments[2])
let evidence = URL(fileURLWithPath: CommandLine.arguments[3])
let variant = CommandLine.arguments[4]
let manifest = try JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("assets/pet-manifest.json"))) as! [String: Any]
let scratch = evidence.appendingPathComponent("\(variant)-scratch-layout.json")
func controller() -> PetController {
    let result = PetController(model: AnimationModel(manifest: manifest), manifest: manifest,
                               assetRoot: root.appendingPathComponent("assets/pet"), layoutURL: scratch,
                               webuiURL: "http://127.0.0.1:1", eventLogURL: nil, snapshotURL: nil)
    result.scale = 1
    result.reducedMotion = false
    result.bubbleMode = "hidden"
    XCTAssertNil(result.panel)
    XCTAssertNil(result.contentView)
    return result
}

// Calls the real controller API with coordinates; does not construct NSEvent.
let taps: [(String, CGFloat, CGFloat, Int, String)] = [
    ("head", 0.5, 0.2, 1, "head_pat"),
    ("body", 0.5, 0.7, 1, "poke"),
    ("tail", 0.9, 0.7, 1, "tail"),
    ("double-body", 0.5, 0.7, 2, "head_pat"),
    ("double-tail", 0.9, 0.7, 2, "head_pat"),
    ("head-boundary", 0.5, 0.45, 1, "poke"),
    ("tail-boundary", 0.72, 0.7, 1, "poke"),
]
for (name, x, y, count, expected) in taps {
    let c = controller()
    let rect = c.petRect()
    let point = CGPoint(x: rect.minX + rect.width * x, y: rect.minY + rect.height * y)
    XCTAssertTrue(PetGeometry.isInteractive(point, pet: rect, bubble: nil))
    c.handleClick(at: point, clickCount: count)
    XCTAssertEqual(c.model.activeClipName, expected)
    let duration = c.model.overlayRemainingMs
    c.model.advance(elapsedMs: duration - 1, nowMs: 0)
    XCTAssertEqual(c.model.activeClipName, expected)
    let frame = c.model.frameIndex
    c.handleClick(at: point, clickCount: count)
    XCTAssertEqual(c.model.frameIndex, frame)
    c.model.advance(elapsedMs: 1, nowMs: 0)
    XCTAssertEqual(c.model.activeClipName, "idle")
    print("PASS controller \(name): \(expected), spam suppressed, completion resumes idle")
}

// Model geometry only: these rectangles represent displays, not actual hardware.
let screens = [CGRect(x: 0, y: 0, width: 1512, height: 982),
               CGRect(x: -1920, y: 50, width: 1920, height: 1080),
               CGRect(x: 200, y: 982, width: 1080, height: 1920)]
for screen in screens {
    for scale: CGFloat in [0.01, 0.55, 1] {
        let size = CGSize(width: 398 * scale, height: 333 * scale)
        for point in [CGPoint(x: -99999, y: -99999), CGPoint(x: 99999, y: 99999),
                      CGPoint(x: -99999, y: 99999), CGPoint(x: 99999, y: -99999)] {
            let placed = PetGeometry.clamp(point, petSize: size, screen: screen)
            let visible = CGRect(origin: placed, size: size).intersection(screen)
            XCTAssertGreaterThanOrEqual(visible.width, size.width * 0.35 - 0.0001)
            XCTAssertGreaterThanOrEqual(visible.height, size.height * 0.35 - 0.0001)
            XCTAssertEqual(PetGeometry.clamp(placed, petSize: size, screen: screen), placed)
        }
    }
}

// Own bitmap contexts only. The real renderer draws into this flipped context.
func render(_ c: PetController) -> (NSBitmapImageRep, Data) {
    let rect = c.petRect()
    let width = Int(ceil(rect.maxX + 25))
    let height = Int(ceil(rect.maxY + 8))
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
                                 bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                 isPlanar: false, colorSpaceName: .deviceRGB,
                                 bitmapFormat: [], bytesPerRow: width * 4, bitsPerPixel: 32)!
    memset(bitmap.bitmapData!, 0, bitmap.bytesPerRow * height)
    let context = NSGraphicsContext(bitmapImageRep: bitmap)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    context.cgContext.translateBy(x: 0, y: CGFloat(height))
    context.cgContext.scaleBy(x: 1, y: -1)
    c.drawPet(in: NSView(frame: CGRect(x: 0, y: 0, width: width, height: height)))
    context.flushGraphics()
    NSGraphicsContext.restoreGraphicsState()
    return (bitmap, Data(bytes: bitmap.bitmapData!, count: bitmap.bytesPerRow * height))
}
let c = controller()
c.scale = 0.55
let hiddenPet = c.petRect()
XCTAssertFalse(PetGeometry.isInteractive(CGPoint(x: hiddenPet.maxX + 2, y: hiddenPet.midY), pet: hiddenPet, bubble: nil))
c.bubbleMode = "always"
let visiblePet = c.petRect()
let card = c.bubbleRect()
XCTAssertTrue(PetGeometry.isInteractive(CGPoint(x: card.midX, y: card.midY), pet: visiblePet, bubble: card))
XCTAssertFalse(PetGeometry.isInteractive(CGPoint(x: card.midX, y: (card.maxY + visiblePet.minY) / 2), pet: visiblePet, bubble: card))
XCTAssertFalse(PetGeometry.isInteractive(CGPoint(x: card.midX, y: card.midY), pet: visiblePet, bubble: nil))
c.bubbleMode = "hidden"
let clips = ["idle", "thinking", "working_search", "waiting", "success", "error", "head_pat", "poke", "tail", "dragging", "dragging_release"]
var renderingCount = 0
var renderingRecords: [[String: Any]] = []
for percent in (variant == "adapted" ? [1, 5, 25, 55, 80, 100] : [55, 80, 100]) {
    c.scale = Double(percent) / 100
    for clip in clips {
        c.model.clearOverlay()
        XCTAssertTrue(c.model.playOverlay(clip))
        let target = c.model.activeClip.frames.count / 2
        c.model.advance(elapsedMs: target * c.model.activeClip.frameMs, nowMs: 0)
        let (bitmap, pixels) = render(c)
        let (_, repeated) = render(c)
        XCTAssertEqual(pixels, repeated)
        let alpha = stride(from: 3, to: pixels.count, by: 4).filter { pixels[$0] != 0 }.count
        XCTAssertGreaterThanOrEqual(alpha, 1)
        let name = "\(variant)-\(clip)-\(percent)"
        try pixels.write(to: evidence.appendingPathComponent("\(name).rgba"))
        try bitmap.representation(using: .png, properties: [:])!.write(to: evidence.appendingPathComponent("\(name).png"))
        renderingRecords.append(["clip": clip, "percent": percent, "frame": c.model.frame,
                                 "pixelsWide": bitmap.pixelsWide, "pixelsHigh": bitmap.pixelsHigh,
                                 "nonzeroAlphaPixels": alpha])
        renderingCount += 1
    }
}
try JSONSerialization.data(withJSONObject: renderingRecords, options: [.prettyPrinted, .sortedKeys])
    .write(to: evidence.appendingPathComponent("\(variant)-render-records.json"))
print("CONTROLLER_RESULT tap_cases=\(taps.count) geometry_cases=36 renders=\(renderingCount) assertions=\(assertionCount) failures=\(assertionFailures)")
exit(assertionFailures == 0 ? 0 : 1)
