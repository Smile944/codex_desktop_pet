import Foundation
import CoreFoundation

/// Manifest-driven pools. Random inputs are supplied by the caller so playback
/// rules can be checked independently of timers, AppKit and random generators.
struct AnimationRules {
    struct Category {
        let id: String
        let weight: Double
        let noMirror: Bool
        let actions: [String]
    }
    struct Choice {
        let kind: String
        let clip: String
    }
    struct MoveParameters {
        let minDist: Double
        let maxDist: Double
        let margin: Double
        let leadSec: Double
        let tailSec: Double
    }
    let idle: [String]
    let turn: [String]
    let drag: [String]
    let clicks: [String]
    let moves: [String]
    let categories: [Category]
    let events: [String: [[String]]]
    let moveParameters: [String: MoveParameters]
    private let weights: [String: Double]

    init(manifest: [String: Any], clipNames: Set<String>) {
        let animations = manifest["animations"] as? [String: Any] ?? [:]
        func names(_ value: Any?) -> [String] {
            (value as? [String] ?? []).filter { clipNames.contains($0) }
        }
        idle = names(animations["idle"])
        turn = names(animations["turn"])
        drag = names(animations["drag"])
        clicks = names(animations["clicks"])
        let rawMoves = animations["moves"] as? [String: Any] ?? [:]
        let defaults = rawMoves["default"] as? [String: Any] ?? [:]
        var parameters: [String: MoveParameters] = [:]
        var moveNames: [String] = []
        func number(_ dict: [String: Any], _ key: String, _ fallback: Double) -> Double {
            guard let value = dict[key] as? NSNumber, CFGetTypeID(value) != CFBooleanGetTypeID(), value.doubleValue.isFinite else { return fallback }
            return value.doubleValue
        }
        for action in rawMoves["actions"] as? [[String: Any]] ?? [] {
            guard let name = action["name"] as? String, clipNames.contains(name) else { continue }
            let merged = defaults.merging(action["params"] as? [String: Any] ?? [:]) { _, new in new }
            let minimum = max(0, number(merged, "minDist", 60))
            parameters[name] = MoveParameters(minDist: minimum, maxDist: max(minimum, number(merged, "maxDist", 240)),
                margin: max(0, number(merged, "margin", 20)), leadSec: max(0, number(merged, "leadSec", 2)), tailSec: max(0, number(merged, "tailSec", 2)))
            moveNames.append(name)
        }
        moves = moveNames
        moveParameters = parameters
        categories = (animations["categories"] as? [[String: Any]] ?? []).compactMap { value in
            guard let id = value["id"] as? String else { return nil }
            let actions = names(value["actions"])
            let weight = max(0, number(value, "weight", 0))
            guard !actions.isEmpty, weight > 0 else { return nil }
            return Category(id: id, weight: weight, noMirror: value["noMirror"] as? Bool ?? false, actions: actions)
        }
        var eventPools: [String: [[String]]] = [:]
        for (event, value) in animations["events"] as? [String: Any] ?? [:] {
            eventPools[event] = (value as? [Any] ?? []).map { band in
                if let name = band as? String { return names([name]) }
                return names(band)
            }
        }
        events = eventPools
        let rawWeights = manifest["animationWeights"] as? [String: Any] ?? [:]
        weights = ["idle": max(0, number(rawWeights, "idle", 10)),
                   "turn": max(0, number(rawWeights, "turn", 5)),
                   "move": max(0, number(rawWeights, "move", 5))]
    }

    /// A configured idle-only pack still needs the manifest scheduler so all
    /// of its idle choices participate instead of falling into legacy micros.
    var hasRandomPools: Bool {
        !idle.isEmpty || !categories.isEmpty || !turn.isEmpty || !moves.isEmpty
    }

    static func pick(_ names: [String], roll: Double, avoiding previous: String? = nil) -> String? {
        let candidates = names.count > 1 ? names.filter { $0 != previous } : names
        guard !candidates.isEmpty else { return nil }
        let unit = roll.isFinite ? min(1, max(0, roll)) : 0
        return candidates[min(candidates.count - 1, Int(unit * Double(candidates.count)))]
    }

    func choose(roll: Double, categoryRoll: Double, actionRoll: Double, mirrored: Bool = false,
                fixed: Bool = false, previous: String? = nil) -> Choice? {
        let idleWeight = idle.isEmpty ? 0 : weights["idle", default: 0]
        let turnWeight = turn.isEmpty ? 0 : weights["turn", default: 0]
        let moveWeight = moves.isEmpty ? 0 : weights["move", default: 0]
        let total = idleWeight + turnWeight + moveWeight + categories.reduce(0) { $0 + $1.weight }
        guard total > 0 else { return idle.first.map { Choice(kind: "idle", clip: $0) } }
        let value = min(0.999999999, max(0, roll.isFinite ? roll : 0)) * total
        if value < idleWeight, let clip = Self.pick(idle, roll: actionRoll, avoiding: previous) { return Choice(kind: "idle", clip: clip) }
        if !fixed, value < idleWeight + turnWeight, let clip = Self.pick(turn, roll: actionRoll, avoiding: previous) { return Choice(kind: "turn", clip: clip) }
        if !fixed, value < idleWeight + turnWeight + moveWeight, let clip = Self.pick(moves, roll: actionRoll, avoiding: previous) { return Choice(kind: "move", clip: clip) }
        let eligible = categories.filter { !(mirrored && $0.noMirror) }
        let sum = eligible.reduce(0) { $0 + $1.weight }
        var ticket = min(0.999999999, max(0, categoryRoll.isFinite ? categoryRoll : 0)) * sum
        for category in eligible {
            if ticket < category.weight, let clip = Self.pick(category.actions, roll: actionRoll, avoiding: previous) {
                return Choice(kind: category.id, clip: clip)
            }
            ticket -= category.weight
        }
        return Self.pick(idle, roll: actionRoll, avoiding: previous).map { Choice(kind: "idle", clip: $0) }
    }

    func event(_ name: String, band: Int, roll: Double, previous: String? = nil) -> String? {
        guard let pool = events[name], pool.indices.contains(band) else { return nil }
        return Self.pick(pool[band], roll: roll, avoiding: previous)
    }

    static func balanceBand(usedPercent: Double) -> Int? {
        guard usedPercent.isFinite, (0...100).contains(usedPercent) else { return nil }
        return min(5, Int(usedPercent / 20))
    }
}

/// One horizontal move with stationary lead/tail footage. The endpoint is
/// planned once and stays inside the selected screen's visible frame.
struct AnimationMotion {
    let start: CGPoint
    let end: CGPoint
    let duration: Double
    let lead: Double
    let tail: Double

    static func plan(start: CGPoint, petSize: CGSize, screen: CGRect, scale: Double,
                     params: AnimationRules.MoveParameters, duration: Double, mirrored: Bool, roll: Double) -> AnimationMotion? {
        guard duration > params.leadSec + params.tailSec, scale > 0, scale.isFinite else { return nil }
        let margin = CGFloat(params.margin)
        let left = screen.minX + margin
        let right = screen.maxX - margin - petSize.width
        guard right >= left, start.x >= left, start.x <= right,
              start.y >= screen.minY, start.y + petSize.height <= screen.maxY else { return nil }
        let available = Double(mirrored ? right - start.x : start.x - left)
        let minimum = params.minDist * scale
        guard available >= minimum else { return nil }
        let maximum = min(available, params.maxDist * scale)
        let distance = minimum + (maximum - minimum) * min(1, max(0, roll.isFinite ? roll : 0))
        let end = CGPoint(x: start.x + CGFloat(mirrored ? distance : -distance), y: start.y)
        return AnimationMotion(start: start, end: end, duration: duration, lead: params.leadSec, tail: params.tailSec)
    }

    func position(at elapsed: Double) -> CGPoint {
        let fraction = min(1, max(0, (elapsed - lead) / (duration - lead - tail)))
        return CGPoint(x: start.x + (end.x - start.x) * fraction, y: start.y)
    }
}
