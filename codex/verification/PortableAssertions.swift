import Foundation

// Deliberately a portable assertion shim, not XCTest or its runner.
var assertionCount = 0
var assertionFailures = 0
class XCTestCase {
    func setUpWithError() throws {}
    func tearDownWithError() throws {}
}
func record(_ pass: Bool, _ description: String, file: StaticString, line: UInt) {
    assertionCount += 1
    if !pass {
        assertionFailures += 1
        print("FAIL \(file):\(line): \(description)")
    }
}
func XCTAssertEqual<T: Equatable>(_ actual: T, _ expected: T, file: StaticString = #filePath, line: UInt = #line) {
    record(actual == expected, "\(actual) != \(expected)", file: file, line: line)
}
func XCTAssertNotEqual<T: Equatable>(_ actual: T, _ expected: T, file: StaticString = #filePath, line: UInt = #line) {
    record(actual != expected, "\(actual) == \(expected)", file: file, line: line)
}
func XCTAssertTrue(_ actual: Bool, file: StaticString = #filePath, line: UInt = #line) {
    record(actual, "expected true", file: file, line: line)
}
func XCTAssertFalse(_ actual: Bool, file: StaticString = #filePath, line: UInt = #line) {
    record(!actual, "expected false", file: file, line: line)
}
func XCTAssertNil<T>(_ actual: T?, file: StaticString = #filePath, line: UInt = #line) {
    record(actual == nil, "expected nil: \(String(describing: actual))", file: file, line: line)
}
func XCTAssertLessThan<T: Comparable>(_ actual: T, _ bound: T, file: StaticString = #filePath, line: UInt = #line) {
    record(actual < bound, "\(actual) >= \(bound)", file: file, line: line)
}
func XCTAssertGreaterThanOrEqual<T: Comparable>(_ actual: T, _ bound: T, file: StaticString = #filePath, line: UInt = #line) {
    record(actual >= bound, "\(actual) < \(bound)", file: file, line: line)
}
