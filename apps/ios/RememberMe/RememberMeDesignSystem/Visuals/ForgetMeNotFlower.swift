import SwiftUI

struct FlowerPetal: Shape {
    func path(in rect: CGRect) -> Path {
        func point(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: rect.minX + x * rect.width, y: rect.minY + y * rect.height)
        }
        var path = Path()
        path.move(to: point(0.5, 1))
        path.addCurve(to: point(0.08, 0.45), control1: point(0.30, 0.84), control2: point(0.04, 0.72))
        path.addCurve(to: point(0.46, 0.035), control1: point(0.01, 0.17), control2: point(0.22, -0.04))
        path.addQuadCurve(to: point(0.54, 0.035), control: point(0.5, 0.065))
        path.addCurve(to: point(0.92, 0.45), control1: point(0.78, -0.04), control2: point(0.99, 0.17))
        path.addCurve(to: point(0.5, 1), control1: point(0.96, 0.72), control2: point(0.70, 0.84))
        path.closeSubpath()
        return path
    }
}

enum RMFlowerState: String, CaseIterable, Identifiable {
    case idle, listening, thinking, speaking, paused, success, unavailable
    var id: String { rawValue }
    var label: String {
        switch self {
        case .idle: "静候"
        case .listening: "倾听"
        case .thinking: "思考"
        case .speaking: "回应"
        case .paused: "暂停"
        case .success: "已保存"
        case .unavailable: "暂不可用"
        }
    }
}

enum RMFlowerMotion {
    static func level(_ value: Double?) -> Double {
        guard let value, value.isFinite else { return 0 }
        return min(1, max(0, value))
    }
    static func paused(reduceMotion: Bool, sceneActive: Bool, visible: Bool, state: RMFlowerState) -> Bool {
        reduceMotion || !sceneActive || !visible || [.paused, .unavailable, .success].contains(state)
    }
    static func scale(time: Double, state: RMFlowerState, amplitude: Double?) -> Double {
        guard time.isFinite, ![.paused, .unavailable, .success].contains(state) else { return 1 }
        let breath = sin(time * .pi * 2 / RMAnimationTokens.breathDuration)
        let base = state == .thinking ? 0.004 : RMAnimationTokens.breathingAmplitude
        // Missing amplitude means state-only motion, never simulated microphone data.
        let reaction = [.listening, .speaking].contains(state) ? level(amplitude) * 0.025 : 0
        return 1 + breath * base + reaction
    }
}

struct ForgetMeNotFlower: View {
    var size: CGFloat = RMMetrics.heroFlower
    var phase: Double = 0
    var amplitude: Double? = nil
    var state: RMFlowerState = .idle
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        ZStack {
            ForEach(0..<5) { index in
                let angle = Double(index) * 72
                FlowerPetal()
                    .fill(RMGradients.petal)
                    .frame(width: size * 0.43, height: size * 0.49)
                    .offset(y: -size * 0.21)
                    .rotationEffect(.degrees(angle + petalAngle(index)))
                if !reduceTransparency && contrast != .increased {
                    FlowerPetal().fill(RMColors.petalLight.opacity(0.2))
                        .frame(width: size * 0.27, height: size * 0.35)
                        .offset(y: -size * 0.22)
                        .rotationEffect(.degrees(angle))
                }
            }
            Circle().fill(RMGradients.center).frame(width: size * 0.18, height: size * 0.18)
            ForEach(0..<5) { index in
                Capsule().fill(RMColors.flowerEye.opacity(0.9))
                    .frame(width: size * 0.025, height: size * 0.065)
                    .offset(y: -size * 0.048).rotationEffect(.degrees(Double(index) * 72))
            }
            Circle().fill(RMColors.flowerStem.opacity(0.7)).frame(width: size * 0.038, height: size * 0.038)
        }.frame(width: size, height: size)
            .opacity(state == .unavailable ? 0.55 : 1)
            .accessibilityHidden(true)
    }
    private func petalAngle(_ index: Int) -> Double {
        guard [.listening, .speaking, .thinking].contains(state) else { return 0 }
        let strength = state == .thinking ? 0.3 : 0.65 + RMFlowerMotion.level(amplitude) * 0.5
        return sin(phase * 0.65 + Double(index) * 0.8) * strength
    }
}

struct VoiceReactiveFlower: View {
    var state: RMFlowerState = .idle
    var audioLevel: Double? = nil
    var size: CGFloat = RMMetrics.heroFlower
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.rmAnimationsDisabled) private var animationsDisabled
    @State private var visible = false
    @State private var smoothedLevel: Double? = nil
    @State private var origin = Date()
    private var paused: Bool {
        RMFlowerMotion.paused(reduceMotion: reduceMotion || animationsDisabled, sceneActive: scenePhase == .active, visible: visible, state: state)
    }
    var body: some View {
        TimelineView(.animation(minimumInterval: RMAnimationTokens.frameInterval, paused: paused)) { timeline in
            let time = paused ? 0 : timeline.date.timeIntervalSince(origin)
            ZStack {
                ForgetMeNotFlower(size: size, phase: time, amplitude: paused ? nil : smoothedLevel, state: state)
                    .scaleEffect(paused ? 1 : RMFlowerMotion.scale(time: time, state: state, amplitude: smoothedLevel))
                if state == .thinking && !paused {
                    ForEach(0..<3) { index in
                        let angle = time * 0.18 + Double(index) * .pi * 2 / 3
                        Circle().fill(RMColors.flowerCenter.opacity(0.55))
                            .frame(width: RMSpacing.xxs, height: RMSpacing.xxs)
                            .offset(x: cos(angle) * size * 0.52, y: sin(angle) * size * 0.42)
                    }
                }
            }.frame(width: size * 1.12, height: size * 1.12)
        }
        .accessibilityHidden(true)
        .onAppear { visible = true; smoothedLevel = audioLevel.map { RMFlowerMotion.level($0) } }
        .onDisappear { visible = false }
        .onChange(of: audioLevel) { _, value in
            guard let value else { smoothedLevel = nil; return }
            let target = RMFlowerMotion.level(value)
            withAnimation(reduceMotion || animationsDisabled ? nil : RMAnimationTokens.audioSmoothing) {
                smoothedLevel = (smoothedLevel ?? target) * 0.6 + target * 0.4
            }
        }
    }
}

struct ForgetMeNotSprig: View {
    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width
            let height = geometry.size.height
            ZStack {
                Canvas { context, _ in
                    var stem = Path()
                    stem.move(to: CGPoint(x: width * 0.51, y: height * 0.92))
                    stem.addCurve(to: CGPoint(x: width * 0.52, y: height * 0.29),
                                  control1: CGPoint(x: width * 0.61, y: height * 0.71),
                                  control2: CGPoint(x: width * 0.42, y: height * 0.42))
                    stem.move(to: CGPoint(x: width * 0.54, y: height * 0.67))
                    stem.addQuadCurve(to: CGPoint(x: width * 0.27, y: height * 0.47),
                                      control: CGPoint(x: width * 0.30, y: height * 0.64))
                    stem.move(to: CGPoint(x: width * 0.52, y: height * 0.48))
                    stem.addQuadCurve(to: CGPoint(x: width * 0.78, y: height * 0.37),
                                      control: CGPoint(x: width * 0.70, y: height * 0.45))
                    context.stroke(stem, with: .color(RMColors.flowerStem.opacity(0.65)), style: StrokeStyle(lineWidth: max(1, width * 0.009), lineCap: .round))
                    var leaf = Path()
                    leaf.move(to: CGPoint(x: width * 0.54, y: height * 0.80))
                    leaf.addQuadCurve(to: CGPoint(x: width * 0.27, y: height * 0.73), control: CGPoint(x: width * 0.33, y: height * 0.65))
                    leaf.addQuadCurve(to: CGPoint(x: width * 0.54, y: height * 0.80), control: CGPoint(x: width * 0.34, y: height * 0.86))
                    context.fill(leaf, with: .color(RMColors.flowerStem.opacity(0.55)))
                }
                ForgetMeNotFlower(size: width * 0.48).position(x: width * 0.51, y: height * 0.30)
                ForgetMeNotFlower(size: width * 0.32).rotationEffect(.degrees(-17)).position(x: width * 0.25, y: height * 0.48)
                ForgetMeNotFlower(size: width * 0.26).rotationEffect(.degrees(14)).position(x: width * 0.78, y: height * 0.37)
            }
        }.accessibilityHidden(true).allowsHitTesting(false)
    }
}

struct RMFlowerSaveFeedback: View {
    var active: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.rmAnimationsDisabled) private var animationsDisabled
    var body: some View {
        ForgetMeNotFlower(size: RMMetrics.inlineFlower, state: .success)
            .scaleEffect(active ? 1 : 0.94)
            .animation(reduceMotion || animationsDisabled ? nil : RMAnimationTokens.transition, value: active)
            .accessibilityHidden(true)
    }
}
