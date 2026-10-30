import Foundation

/// Port of the original `runtime/animation_model.py` — a pure animation state
/// machine with no UI dependency. Keeps durable DSH state separate from
/// temporary visual overlays so a click, idle micro-animation, or success
/// pulse always returns to the newest Agent state.
final class AnimationModel {
    struct Clip {
        let name: String
        let frames: [String]
        let frameMs: Int
        let loop: Bool
    }

    static let states: Set<String> = [
        "IDLE", "THINKING", "WORKING", "WAITING", "SUCCESS", "ERROR", "DISCONNECTED",
    ]

    private static let dragClips: Set<String> = ["dragging", "dragging_release"]
    private static let interactionClips: Set<String> = ["head_pat", "poke", "tail"]

    /// Fade clip changes only; never blend successive 24 fps video frames.
    static func crossfadeDuration(previousClip: String, currentClip: String) -> Double? {
        if previousClip == currentClip || dragClips.contains(previousClip) || dragClips.contains(currentClip) {
            return nil
        }
        return 0.10
    }

    enum OverlayPurpose { case decoration, interaction, manual, drag }
    private(set) var rules: AnimationRules!
    private(set) var mirrored = false
    private(set) var overlayPurpose: OverlayPurpose?
    private var overlayLoop: Bool?
    private var turnsOnCompletion = false
    private var lastEvents: [String: String] = [:]
    private var dragMap: [String: String] = [:]

    private(set) var clips: [String: Clip] = [:]
    private var stateMap: [String: String] = [:]
    private var workingActivityMap: [String: String] = [:]
    private(set) var idleMicroClips: [String] = []
    private var idleMicroIntervalsMs: [String: [Int]] = [:]
    private var interactionCooldownMs = 1200
    private var lastInteractionMs: Int?
    private var lastIdleMicro: String?
    private var lastAmbientClip: String?

    private(set) var baseState = "IDLE"
    private(set) var baseActivity: String?
    private(set) var baseClipName = "idle"
    private(set) var overlayClipName: String?
    private(set) var pulseState: String?
    private(set) var pulseDeadlineMs: Int?
    private(set) var pulseClipName: String?
    private(set) var activeClipName = "idle"
    private(set) var frameIndex = 0
    private(set) var frameElapsedMs = 0

    init(manifest: [String: Any]) {
        if let clipsDict = manifest["clips"] as? [String: Any] {
            for (name, value) in clipsDict {
                guard let v = value as? [String: Any],
                      let frames = v["frames"] as? [String], !frames.isEmpty else { continue }
                clips[name] = Clip(
                    name: name,
                    frames: frames,
                    frameMs: max(1, Self.asInt(v["frameMs"], fallback: 180)),
                    loop: (v["loop"] as? Bool) ?? false
                )
            }
        }
        if let map = manifest["stateMap"] as? [String: String] { stateMap = map }
        if let map = manifest["workingActivityMap"] as? [String: String] { workingActivityMap = map }
        if let micros = manifest["idleMicroClips"] as? [String] { idleMicroClips = micros }
        idleMicroIntervalsMs = manifest["idleMicroIntervalsMs"] as? [String: [Int]] ?? [
            "quiet": [45000, 90000], "normal": [25000, 45000], "lively": [12000, 22000],
        ]
        interactionCooldownMs = Self.asInt(manifest["interactionCooldownMs"], fallback: 1200)
        rules = AnimationRules(manifest: manifest, clipNames: Set(clips.keys))
        dragMap = manifest["dragMap"] as? [String: String] ?? [:]
        if let idleClip = stateMap["IDLE"].flatMap({ clips[$0] == nil ? nil : $0 }) ?? rules.idle.first ?? clips.keys.sorted().first {
            baseClipName = idleClip
            activeClipName = idleClip
        }
    }

    var activeClip: Clip {
        clips[activeClipName] ?? Clip(name: activeClipName, frames: [], frameMs: 180, loop: false)
    }

    var frame: String {
        activeClip.frames.isEmpty ? "" : activeClip.frames[frameIndex]
    }

    private var activeLoops: Bool { overlayClipName == nil ? activeClip.loop : (overlayLoop ?? activeClip.loop) }

    var overlayRemainingMs: Int {
        guard overlayClipName != nil, !activeLoops else { return 0 }
        return (activeClip.frames.count - frameIndex) * activeClip.frameMs - frameElapsedMs
    }

    func idleMicroInterval(activityLevel: String) -> ClosedRange<Int> {
        let pair = idleMicroIntervalsMs[activityLevel] ?? idleMicroIntervalsMs["normal"] ?? [25000, 45000]
        guard pair.count == 2, pair[0] >= 0, pair[1] >= pair[0] else { return 25000...45000 }
        return pair[0]...pair[1]
    }

    func applyState(_ state: String, activity: String? = nil) {
        guard Self.states.contains(state) else { return }
        let repeated = baseState == state && baseActivity == activity
        baseState = state
        baseActivity = activity
        if !repeated { baseClipName = clip(for: state, activity: activity) }
        if state != "IDLE" {
            pulseState = nil
            pulseDeadlineMs = nil
            pulseClipName = nil
            let manualContinues = overlayPurpose == .manual && state != "WAITING" && state != "ERROR"
            if overlayPurpose != .drag && !manualContinues { resetOverlay() }
        }
        if overlayClipName == nil {
            activate(underlayClipName)
        }
    }

    func applyPulse(state: String, ttlMs: Int, nowMs: Int, resumeState: String?, resumeActivity: String?, completeClip: Bool = true) {
        guard Self.states.contains(state), ttlMs > 0 else { return }
        if let resume = resumeState, Self.states.contains(resume) {
            baseState = resume
            baseActivity = resumeActivity
            baseClipName = clip(for: resume, activity: resumeActivity)
        }
        let repeatedPulse = pulseState == state
        let previousDeadline = repeatedPulse ? pulseDeadlineMs : nil
        pulseState = state
        pulseClipName = repeatedPulse ? (pulseClipName ?? clip(for: state, activity: nil)) : clip(for: state, activity: nil)
        let pulseClip = clips[pulseClipName ?? ""]
        let duration = completeClip ? (pulseClip?.frames.count ?? 0) * (pulseClip?.frameMs ?? 0) : 0
        pulseDeadlineMs = max(nowMs + ttlMs, previousDeadline ?? nowMs + duration)
        if overlayPurpose != .drag { resetOverlay() }
        if overlayClipName == nil {
            activate(pulseClipName ?? baseClipName)
        }
    }

    @discardableResult
    func playOverlay(_ clipName: String) -> Bool {
        startOverlay(clipName, purpose: Self.dragClips.contains(clipName) || dragMap.values.contains(clipName) || rules.drag.contains(clipName) ? .drag : .decoration)
    }

    @discardableResult
    private func startOverlay(_ clipName: String, purpose: OverlayPurpose, loop: Bool? = nil, restart: Bool = false, turns: Bool = false) -> Bool {
        guard clips[clipName] != nil else { return false }
        overlayClipName = clipName
        overlayPurpose = purpose
        overlayLoop = loop
        turnsOnCompletion = turns
        activate(clipName, restart: restart)
        return true
    }

    func clearOverlay() {
        resetOverlay()
        activate(underlayClipName)
    }

    private func resetOverlay() {
        overlayClipName = nil
        overlayPurpose = nil
        overlayLoop = nil
        turnsOnCompletion = false
    }

    @discardableResult
    func playManual(_ clipName: String) -> Bool {
        guard overlayPurpose != .drag, pulseState == nil, baseState != "WAITING" else { return false }
        return startOverlay(clipName, purpose: .manual, loop: false, restart: true, turns: rules.turn.contains(clipName))
    }

    func nextAmbient(roll: Double, categoryRoll: Double, actionRoll: Double) -> AnimationRules.Choice? {
        rules.choose(roll: roll, categoryRoll: categoryRoll, actionRoll: actionRoll,
            mirrored: mirrored, previous: lastAmbientClip ?? activeClipName)
    }

    @discardableResult
    func playAmbient(_ choice: AnimationRules.Choice) -> Bool {
        guard baseState == "IDLE", pulseState == nil, overlayClipName == nil else { return false }
        guard startOverlay(choice.clip, purpose: .decoration, loop: false, restart: true, turns: choice.kind == "turn") else { return false }
        lastAmbientClip = choice.clip
        return true
    }

    func dragClip(release: Bool = false) -> String? {
        let key = release ? "release" : "dragging"
        if let mapped = dragMap[key] ?? dragMap[release ? "dragging_release" : "drag"], clips[mapped] != nil { return mapped }
        let legacy = release ? "dragging_release" : "dragging"
        if clips[legacy] != nil { return legacy }
        return release ? nil : rules.drag.first
    }

    @discardableResult
    func playDrag(release: Bool = false) -> Bool {
        guard let name = dragClip(release: release) else { return false }
        return startOverlay(name, purpose: .drag, loop: !release, restart: true)
    }

    @discardableResult
    func playEvent(_ event: String, band: Int, roll: Double) -> Bool {
        guard baseState == "IDLE", pulseState == nil, overlayClipName == nil,
              let name = rules.event(event, band: band, roll: roll, previous: lastEvents["\(event):\(band)"]) else { return false }
        lastEvents["\(event):\(band)"] = name
        return startOverlay(name, purpose: .decoration, loop: false, restart: true)
    }

    @discardableResult
    func playInteraction(_ clipName: String, nowMs: Int) -> Bool {
        guard (Self.interactionClips.contains(clipName) || rules.clicks.contains(clipName)), pulseState == nil, baseState != "WAITING" else { return false }
        guard overlayPurpose != .interaction, overlayPurpose != .drag, overlayPurpose != .manual else { return false }
        if let last = lastInteractionMs, nowMs - last < interactionCooldownMs { return false }
        guard startOverlay(clipName, purpose: .interaction, loop: false, restart: true) else { return false }
        lastInteractionMs = nowMs
        return true
    }

    @discardableResult
    func playIdleMicro(index: Int = 0) -> Bool {
        guard baseState == "IDLE", overlayClipName == nil, pulseState == nil else { return false }
        guard !idleMicroClips.isEmpty else { return false }
        var name = idleMicroClips[index % idleMicroClips.count]
        if idleMicroClips.count > 1, name == lastIdleMicro {
            name = idleMicroClips[(index + 1) % idleMicroClips.count]
        }
        lastIdleMicro = name
        return playOverlay(name)
    }

    func advance(elapsedMs: Int, nowMs: Int) {
        guard elapsedMs >= 0 else { return }
        var elapsed = elapsedMs
        if let deadline = pulseDeadlineMs, nowMs >= deadline {
            pulseState = nil
            pulseDeadlineMs = nil
            pulseClipName = nil
            if overlayClipName == nil {
                activate(baseClipName)
                elapsed = 0
            }
        }

        let clip = activeClip
        guard !clip.frames.isEmpty else { return }
        let total = frameElapsedMs + elapsed
        let nextFrame = frameIndex + total / clip.frameMs
        frameElapsedMs = total % clip.frameMs
        if nextFrame < clip.frames.count {
            frameIndex = nextFrame
        } else if activeLoops {
            frameIndex = nextFrame % clip.frames.count
        } else if overlayClipName != nil {
            if turnsOnCompletion { mirrored.toggle() }
            resetOverlay()
            activate(underlayClipName, restart: true)
        } else {
            frameIndex = clip.frames.count - 1
            frameElapsedMs = 0
        }
    }

    func clip(for state: String, activity: String?) -> String {
        if state == "WORKING", let activity = activity, let mapped = workingActivityMap[activity], clips[mapped] != nil {
            return mapped
        }
        if let mapped = stateMap[state], clips[mapped] != nil { return mapped }
        let bands = ["THINKING": 0, "WORKING": 1, "WAITING": 3, "SUCCESS": 4, "ERROR": 5]
        if let band = bands[state], let event = rules.event("workStatus", band: band, roll: 0) { return event }
        return stateMap["IDLE"].flatMap { clips[$0] == nil ? nil : $0 } ?? rules.idle.first ?? baseClipName
    }

    private var underlayClipName: String {
        pulseClipName ?? baseClipName
    }

    private func activate(_ clipName: String, restart: Bool = false) {
        guard restart || activeClipName != clipName else { return }
        activeClipName = clipName
        frameIndex = 0
        frameElapsedMs = 0
    }

    private static func asInt(_ value: Any?, fallback: Int) -> Int {
        if let i = value as? Int { return i }
        if let d = value as? Double { return Int(d) }
        if let s = value as? String { return Int(s) ?? fallback }
        return fallback
    }
}
