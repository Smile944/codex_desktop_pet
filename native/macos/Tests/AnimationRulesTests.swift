import XCTest
@testable import BigFishCore

final class AnimationRulesTests: XCTestCase {
    private func rules() -> AnimationRules {
        AnimationRules(manifest: ["animations": ["idle": ["idle"], "turn": ["turn"], "drag": ["drag"], "clicks": ["click1", "click2"],
            "moves": ["default": ["minDist": 60, "maxDist": 240, "margin": 20, "leadSec": 2, "tailSec": 2], "actions": [["name": "walk"]]],
            "categories": [["id": "fun", "weight": 70, "actions": ["fun1", "fun2"]], ["id": "text", "weight": 10, "noMirror": true, "actions": ["text"]]],
            "events": ["balance": ["b0", "b1", "b2", "b3", "b4", "b5"]]], "animationWeights": ["idle": 10, "turn": 5, "move": 5]],
            clipNames: Set(["idle", "turn", "drag", "click1", "click2", "walk", "fun1", "fun2", "text", "b0", "b1", "b2", "b3", "b4", "b5"]))
    }
    func testHierarchicalWeightsAtEveryTopLevelBoundary() {
        let r = rules()
        XCTAssertEqual(r.choose(roll: 0.099, categoryRoll: 0, actionRoll: 0)?.kind, "idle")
        XCTAssertEqual(r.choose(roll: 0.10, categoryRoll: 0, actionRoll: 0)?.kind, "turn")
        XCTAssertEqual(r.choose(roll: 0.15, categoryRoll: 0, actionRoll: 0)?.kind, "move")
        XCTAssertEqual(r.choose(roll: 0.20, categoryRoll: 0, actionRoll: 0)?.kind, "fun")
        XCTAssertEqual(r.choose(roll: 0.99, categoryRoll: 0.99, actionRoll: 0)?.clip, "text")
        XCTAssertEqual(r.choose(roll: 0.5, categoryRoll: 0, actionRoll: 0.99)?.clip, "fun2")
    }
    func testFixedDisablesMovementAndMirroringExcludesText() {
        let r = rules()
        XCTAssertEqual(r.choose(roll: 0.10, categoryRoll: 0.99, actionRoll: 0, mirrored: true, fixed: true)?.kind, "fun")
        XCTAssertEqual(r.choose(roll: 0.99, categoryRoll: 0.99, actionRoll: 0, mirrored: true)?.clip, "fun1")
    }
    func testQuotaUsesActualUsedPercentageBoundaries() {
        let r = rules()
        for (p, expected) in [(0.0, "b0"), (19.99, "b0"), (20, "b1"), (99.99, "b4"), (100, "b5")] {
            XCTAssertEqual(r.event("balance", band: AnimationRules.balanceBand(usedPercent: p)!, roll: 0), expected)
        }
        XCTAssertNil(AnimationRules.balanceBand(usedPercent: Double.nan))
        XCTAssertNil(AnimationRules.balanceBand(usedPercent: -1))
    }
    func testMoveHoldsStartAndTailAndStaysInsideScreen() {
        let plan = AnimationMotion.plan(start: CGPoint(x: 100, y: 40), petSize: CGSize(width: 100, height: 80),
            screen: CGRect(x: 0, y: 0, width: 400, height: 300), scale: 0.5,
            params: AnimationRules.MoveParameters(minDist: 60, maxDist: 240, margin: 20, leadSec: 2, tailSec: 2),
            duration: 10, mirrored: true, roll: 1)!
        XCTAssertEqual(plan.position(at: 2), CGPoint(x: 100, y: 40))
        XCTAssertEqual(plan.position(at: 5), CGPoint(x: 160, y: 40))
        XCTAssertEqual(plan.position(at: 8), CGPoint(x: 220, y: 40))
        XCTAssertEqual(plan.position(at: 50), CGPoint(x: 220, y: 40))
        XCTAssertNil(AnimationMotion.plan(start: CGPoint(x: 275, y: 40), petSize: CGSize(width: 100, height: 80),
            screen: CGRect(x: 0, y: 0, width: 400, height: 300), scale: 1,
            params: AnimationRules.MoveParameters(minDist: 60, maxDist: 240, margin: 20, leadSec: 2, tailSec: 2),
            duration: 10, mirrored: true, roll: 0))
    }
    func testIdleOnlyCustomPackUsesConfiguredSchedulingAndAlternates() {
        let r = AnimationRules(manifest: ["animations": ["idle": ["idle-a", "idle-b"]]], clipNames: ["idle-a", "idle-b"])
        XCTAssertTrue(r.hasRandomPools)
        XCTAssertEqual(r.choose(roll: 0.5, categoryRoll: 0, actionRoll: 0, previous: "idle-a")?.clip, "idle-b")
        XCTAssertEqual(r.choose(roll: 0.5, categoryRoll: 0, actionRoll: 0, previous: "idle-b")?.clip, "idle-a")
        XCTAssertFalse(AnimationRules(manifest: [:], clipNames: ["idle"]).hasRandomPools)
    }

}
