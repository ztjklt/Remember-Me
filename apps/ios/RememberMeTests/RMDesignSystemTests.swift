import XCTest
import UIKit
import SwiftUI
@testable import RememberMe

@MainActor
final class RMDesignSystemTests: XCTestCase {
    func testDecorativeTimelinesStopForAccessibilityBackgroundAndHiddenScreens() {
        XCTAssertTrue(RMFlowerMotion.paused(reduceMotion: true, sceneActive: true, visible: true, state: .listening))
        XCTAssertTrue(RMFlowerMotion.paused(reduceMotion: false, sceneActive: false, visible: true, state: .speaking))
        XCTAssertTrue(RMFlowerMotion.paused(reduceMotion: false, sceneActive: true, visible: false, state: .thinking))
        XCTAssertTrue(RMFlowerMotion.paused(reduceMotion: false, sceneActive: true, visible: true, state: .paused))
        XCTAssertFalse(RMFlowerMotion.paused(reduceMotion: false, sceneActive: true, visible: true, state: .listening))
    }
    func testAbsentOrInvalidAudioNeverBecomesAFalseReactiveSignal() {
        XCTAssertEqual(RMFlowerMotion.level(nil), 0)
        XCTAssertEqual(RMFlowerMotion.level(.nan), 0)
        XCTAssertEqual(RMFlowerMotion.level(.infinity), 0)
        XCTAssertEqual(RMFlowerMotion.level(-0.5), 0)
        XCTAssertEqual(RMFlowerMotion.level(4), 1)
        XCTAssertEqual(RMFlowerMotion.scale(time: .nan, state: .listening, amplitude: 1), 1)
        XCTAssertEqual(RMFlowerMotion.scale(time: 2, state: .paused, amplitude: 1), 1)
        for time in stride(from: 0.0, to: 20, by: 0.25) {
            let scale = RMFlowerMotion.scale(time: time, state: .speaking, amplitude: 1)
            XCTAssertGreaterThanOrEqual(scale, 0.988)
            XCTAssertLessThanOrEqual(scale, 1.0371)
        }
    }
    func testTwinHaloUsesOnlyMeasuredFiniteEnergyAndStaysWithinItsAllocatedSquare() {
        for invalid in [Double?.none, -.infinity, .infinity, .nan, -1] {
            XCTAssertEqual(RMTwinAudioMotion.level(invalid), 0)
        }
        XCTAssertEqual(RMTwinAudioMotion.level(3), 1)
        for index in 0..<112 {
            XCTAssertEqual(RMTwinAudioMotion.rayLength(index: index, amplitude: 0), 0)
            XCTAssertEqual(RMTwinAudioMotion.rayLength(index: index, amplitude: .nan), 0)
            for amplitude in stride(from: 0.01, through: 1.0, by: 0.05) {
                let length = RMTwinAudioMotion.rayLength(index: index, amplitude: amplitude)
                XCTAssertGreaterThan(length, 0)
                XCTAssertLessThanOrEqual(0.397 + length + 0.003, 0.49)
            }
        }
        let quiet = (0..<112).map { RMTwinAudioMotion.rayLength(index: $0, amplitude: 0.05) }.reduce(0, +)
        let loud = (0..<112).map { RMTwinAudioMotion.rayLength(index: $0, amplitude: 0.9) }.reduce(0, +)
        XCTAssertGreaterThan(loud, quiet * 2)
    }
    func testTwinHaloAttacksQuicklyAndFinishesItsReleaseAtSilence() {
        let attack = RMTwinAudioMotion.envelope(previous: 0, target: 1, elapsed: RMTwinAudioMotion.frameInterval)
        XCTAssertGreaterThan(attack, 0.5)
        XCTAssertLessThan(attack, 1)
        let release = RMTwinAudioMotion.envelope(previous: 1, target: 0, elapsed: RMTwinAudioMotion.frameInterval)
        XCTAssertGreaterThan(release, 0.7)
        XCTAssertLessThan(release, 1)
        var level = 1.0
        for _ in 0..<30 {
            level = RMTwinAudioMotion.envelope(previous: level, target: 0, elapsed: RMTwinAudioMotion.frameInterval)
        }
        XCTAssertEqual(level, 0)
        XCTAssertEqual(RMTwinAudioMotion.envelope(previous: 0.4, target: 1, elapsed: .nan), 0.4)
        XCTAssertEqual(RMTwinAudioMotion.envelope(previous: .nan, target: .infinity, elapsed: 1), 0)
    }
    func testTwinHaloStopsItsClockForSilenceAccessibilityAndInactiveScreens() {
        func runs(reduceMotion: Bool = false, animationsDisabled: Bool = false, sceneActive: Bool = true,
                  visible: Bool = true, state: RMFlowerState = .speaking, target: Double = 0.4,
                  envelope: Double = 0) -> Bool {
            RMTwinAudioMotion.runs(reduceMotion: reduceMotion, animationsDisabled: animationsDisabled,
                                  sceneActive: sceneActive, visible: visible, state: state,
                                  target: target, envelope: envelope)
        }
        XCTAssertTrue(runs())
        XCTAssertTrue(runs(target: 0, envelope: 0.2))
        XCTAssertFalse(runs(target: 0, envelope: 0))
        XCTAssertFalse(runs(target: .nan, envelope: .infinity))
        XCTAssertFalse(runs(reduceMotion: true))
        XCTAssertFalse(runs(animationsDisabled: true))
        XCTAssertFalse(runs(sceneActive: false))
        XCTAssertFalse(runs(visible: false))
        for state in [RMFlowerState.idle, .thinking, .paused, .success, .unavailable] {
            XCTAssertFalse(runs(state: state))
        }
    }
    func testSemanticTextAndActionPairsRemainReadableInBothAppearances() {
        for appearance in [UIUserInterfaceStyle.light, .dark] {
            let traits = UITraitCollection(userInterfaceStyle: appearance)
            func resolved(_ color: Color) -> UIColor { UIColor(color).resolvedColor(with: traits) }
            for background in [RMColors.background, RMColors.surface, RMColors.subtle, RMColors.floralSurface] {
                XCTAssertGreaterThanOrEqual(contrast(resolved(RMColors.text), resolved(background)), 4.5)
                XCTAssertGreaterThanOrEqual(contrast(resolved(RMColors.secondaryText), resolved(background)), 4.5)
                XCTAssertGreaterThanOrEqual(contrast(resolved(RMColors.action), resolved(background)), 4.5)
            }
            XCTAssertGreaterThanOrEqual(contrast(resolved(RMColors.onAction), resolved(RMColors.action)), 4.5)
            XCTAssertGreaterThanOrEqual(contrast(resolved(RMColors.onDanger), resolved(RMColors.danger)), 4.5)
        }
    }
    func testInvalidDateIsPreservedInsteadOfInventingAnEventTime() {
        XCTAssertEqual(RMDateLabel.string("时间待核对"), "时间待核对")
        XCTAssertNotEqual(RMDateLabel.string("2026-10-12T12:00:00Z"), "2026-10-12T12:00:00Z")
    }
    private func contrast(_ lhs: UIColor, _ rhs: UIColor) -> CGFloat {
        func luminance(_ color: UIColor) -> CGFloat {
            var red: CGFloat = 0, green: CGFloat = 0, blue: CGFloat = 0, alpha: CGFloat = 0
            XCTAssertTrue(color.getRed(&red, green: &green, blue: &blue, alpha: &alpha))
            func linear(_ value: CGFloat) -> CGFloat { value <= 0.04045 ? value / 12.92 : pow((value + 0.055) / 1.055, 2.4) }
            return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)
        }
        let a = luminance(lhs), b = luminance(rhs)
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)
    }
}
