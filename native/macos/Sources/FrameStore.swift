import AppKit

/// Owns only a bounded working set of decoded frames. Construction never reads
/// assets; expanding the library therefore does not increase startup residency.
final class FrameStore {
    private struct Entry { let image: NSImage; let cost: Int }
    private let root: URL
    private let allowed: Set<String>
    private let countLimit: Int
    private let byteLimit: Int
    private var entries: [String: Entry] = [:]
    private var recency: [String] = []
    private(set) var residentBytes = 0
    var residentFrameCount: Int { entries.count }

    init(root: URL, frames: Set<String>, countLimit: Int = 24, byteLimit: Int = 24 * 640 * 360 * 4) {
        self.root = root.resolvingSymlinksInPath().standardizedFileURL
        self.allowed = frames
        self.countLimit = max(1, countLimit)
        self.byteLimit = max(1, byteLimit)
    }

    func image(for frame: String) -> NSImage? {
        if let entry = entries[frame] {
            recency.removeAll { $0 == frame }
            recency.append(frame)
            return entry.image
        }
        guard allowed.contains(frame), !frame.hasPrefix("/"), !frame.split(separator: "/").contains("..") else { return nil }
        let file = root.appendingPathComponent(frame).resolvingSymlinksInPath().standardizedFileURL
        guard file.path.hasPrefix(root.path + "/"),
              let data = try? Data(contentsOf: file), let source = NSImage(data: data),
              let cg = source.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return nil }
        let image = NSImage(cgImage: cg, size: NSSize(width: cg.width, height: cg.height))
        let cost = cg.bytesPerRow * cg.height
        guard cost <= byteLimit else { return image }
        while !recency.isEmpty, entries.count >= countLimit || residentBytes + cost > byteLimit {
            let oldest = recency.removeFirst()
            if let removed = entries.removeValue(forKey: oldest) { residentBytes -= removed.cost }
        }
        entries[frame] = Entry(image: image, cost: cost)
        recency.append(frame)
        residentBytes += cost
        return image
    }
}
