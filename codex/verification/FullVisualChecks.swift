import AppKit
import CryptoKit

// Transport stub only; no application, windows, timers, input, or notifications start.
final class ProtocolIO {
    static let shared = ProtocolIO()
    func write(_ object: [String: Any]) {}
}
let root = URL(fileURLWithPath: CommandLine.arguments[2])
let evidence = URL(fileURLWithPath: CommandLine.arguments[3])
let variant = CommandLine.arguments[4]
let manifest = try JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("assets/pet-manifest.json"))) as! [String: Any]
let c = PetController(model: AnimationModel(manifest: manifest), manifest: manifest,
                      assetRoot: root.appendingPathComponent("assets/pet"),
                      layoutURL: evidence.appendingPathComponent("nonexistent-layout.json"),
                      webuiURL: "http://127.0.0.1:1", eventLogURL: nil, snapshotURL: nil)
precondition(c.panel == nil && c.contentView == nil)
c.soundEnabled = false
c.soundStates = []
c.openLabel = "Host"
let output = evidence.appendingPathComponent("\(variant)-cases.jsonl")
FileManager.default.createFile(atPath: output.path, contents: nil)
let stream = try FileHandle(forWritingTo: output)
var count = 0
let filterURL = evidence.appendingPathComponent("rerender.json")
let filter: Set<String>? = FileManager.default.fileExists(atPath: filterURL.path) ? Set(try JSONDecoder().decode([String].self, from: Data(contentsOf: filterURL))) : nil

func render(_ id: String, group: String, representative: Bool = false) {
    if let filter = filter, !filter.contains(id) { return }
    autoreleasepool {
        c.verificationSettleFade() // Temporary-copy hook: test settled static output, never sample the wall clock.
        let pet = c.petRect(), bubble = c.bubbleRect()
        let width = Int(ceil(max(pet.maxX + 50, c.bubbleMode == "hidden" ? 0 : bubble.maxX + 14)))
        let height = Int(ceil(pet.maxY + 8))
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
                                     bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                     colorSpaceName: .deviceRGB, bitmapFormat: [], bytesPerRow: width * 4, bitsPerPixel: 32)!
        memset(bitmap.bitmapData!, 0, bitmap.bytesPerRow * height)
        let context = NSGraphicsContext(bitmapImageRep: bitmap)!
        NSGraphicsContext.saveGraphicsState()
        context.cgContext.translateBy(x: 0, y: CGFloat(height))
        context.cgContext.scaleBy(x: 1, y: -1)
        NSGraphicsContext.current = NSGraphicsContext(cgContext: context.cgContext, flipped: true)
        let view = PetView(frame: NSRect(x: 0, y: 0, width: width, height: height))
        view.controller = c
        view.draw(view.bounds) // Exercises the actual PetView.drawPet + drawCard composition.
        context.flushGraphics()
        NSGraphicsContext.restoreGraphicsState()
        let pixels = Data(bytes: bitmap.bitmapData!, count: bitmap.bytesPerRow * height)
        precondition(stride(from: 3, to: pixels.count, by: 4).contains { pixels[$0] != 0 }, "Empty bitmap: \(id)")
        let hash = SHA256.hash(data: pixels).map { String(format: "%02x", $0) }.joined()
        let row: [String: Any] = ["id": id, "group": group, "width": width, "height": height,
                                  "bytes": pixels.count, "sha256": hash, "frame": c.model.frame]
        let json = try! JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
        stream.write(json); stream.write(Data([10]))
        if filter != nil || representative {
            try! bitmap.representation(using: .png, properties: [:])!.write(to: evidence.appendingPathComponent("\(variant)-\(id).png"))
            if filter != nil { try! pixels.write(to: evidence.appendingPathComponent("\(variant)-\(id).rgba")) }
        }
        count += 1
        if count % 5000 == 0 { print("PROGRESS \(variant) renders=\(count)"); fflush(stdout) }
    }
}

let sizes = [55, 80, 100]
for percent in sizes {
    c.scale = Double(percent) / 100; c.bubbleMode = "hidden"
    for clip in c.model.clips.keys.sorted() {
        c.model.playOverlay(clip == "idle" ? "thinking" : "idle")
        c.model.playOverlay(clip)
        let frames = c.model.activeClip.frames.count
        for index in 0..<frames {
            precondition(c.model.frameIndex == index && c.model.activeClipName == clip)
            render("frame-\(clip)-\(index)-\(percent)", group: "frames",
                   representative: percent == 100 && [0, frames / 2, frames - 1].contains(index))
            c.model.advance(elapsedMs: c.model.activeClip.frameMs, nowMs: 0)
        }
    }
}

let states = AnimationModel.states.sorted()
let activities = ["none"] + ((manifest["workingActivityMap"] as! [String: String]).keys.sorted())
let profiles = ["status", "long", "empty-detail", "overlay", "task1", "task2", "task3", "task4", "footer", "task-footer", "no-card", "fallback-footer"]
for state in states {
 for activity in activities {
  for percent in sizes {
   for bubblePercent in [80, 100, 120] {
    for mode in ["always", "hidden", "custom"] {
     for level in ["quiet", "normal", "lively"] {
      for reduced in [false, true] {
       for profile in profiles {
        c.scale = Double(percent) / 100; c.bubbleScale = Double(bubblePercent) / 100
        c.bubbleMode = mode; c.activityLevel = level; c.reducedMotion = reduced
        c.bubbleStates = ["WAITING", "ERROR", "SUCCESS"]
        c.tasks = []; c.balanceSummary = ""; c.overlayMessage = ""; c.overlayState = nil; c.overlayDeadlineMs = nil
        var message: [String: Any] = ["kind": "state", "state": state,
                                    "message": "统一状态标题 · Host", "detail": "统一详情 ABC 123 · 中文排版"]
        if activity != "none" { message["activity"] = activity }
        c.apply(message)
        c.statusDeadlineMs = nil
        // Reset to frame zero even when this state reuses the previous clip.
        c.model.playOverlay(c.model.baseClipName == "idle" ? "thinking" : "idle")
        c.model.clearOverlay()
        switch profile {
        case "long": c.statusMessage = String(repeating: "长标题 ABC 超出文字框 ", count: 12); c.statusDetail = String(repeating: "多行详情 123\n", count: 12)
        case "empty-detail": c.statusDetail = ""
        case "overlay": c.overlayMessage = "临时互动标题 · Host"; c.overlayDetail = "临时详情"; c.overlayState = "APPROVAL"
        case "no-card": c.statusMessage = ""
        case "fallback-footer": c.statusMessage = ""; c.balanceSummary = "余额 · 1234 tokens · Host"
        case "footer": c.balanceSummary = "余额 · 1234 tokens · Host"
        default: break
        }
        if profile.hasPrefix("task") {
            let n = profile == "task-footer" ? 4 : Int(profile.suffix(1))!
            for index in 0..<n {
                let row: [String: Any]
                switch index {
                case 0: row = ["state": state, "project": "项目中文 ABC 123"]
                case 1: row = ["state": state, "task": String(repeating: "任务长文案 ", count: 20)]
                case 2: row = ["state": state, "message": "消息回退"]
                default: row = ["state": state]
                }
                c.tasks.append(row)
            }
            if profile == "task-footer" { c.balanceSummary = "余额 · 1234 tokens · Host" }
        }
        let id = "card-\(state)-\(activity)-\(percent)-\(bubblePercent)-\(mode)-\(level)-\(reduced ? 1 : 0)-\(profile)"
        render(id, group: "cards", representative: state == "WORKING" && activity == "searching" && percent == 55 && bubblePercent == 100 && mode == "always" && level == "normal" && !reduced)
       }
      }
     }
    }
   }
  }
 }
}
// Explicit custom visibility sets exercise match and nonmatch for every state.
for state in states {
 for allowed in [false, true] {
    c.bubbleMode = "custom"; c.scale = 1; c.bubbleScale = 1; c.tasks = []; c.balanceSummary = ""
    c.overlayMessage = ""; c.overlayState = nil; c.statusState = state; c.statusMessage = "统一自定义气泡"; c.statusDetail = "匹配状态列表"; c.statusDeadlineMs = nil
    c.bubbleStates = allowed ? [state] : []
    render("visibility-\(state)-\(allowed ? 1 : 0)", group: "visibility")
 }
}
try stream.close()
print("FULL_VISUAL_RESULT variant=\(variant) renders=\(count) windows=0 input=0")
