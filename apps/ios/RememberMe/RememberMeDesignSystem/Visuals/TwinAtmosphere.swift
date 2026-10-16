import SwiftUI

/// The Twin's night palette stays consistent with the film in either system appearance.
enum RMTwinColors {
    static let background = Color(red: 0.025, green: 0.055, blue: 0.105)
    static let surface = Color(red: 0.055, green: 0.105, blue: 0.175)
    static let raisedSurface = Color(red: 0.085, green: 0.155, blue: 0.245)
    static let text = Color(red: 0.95, green: 0.975, blue: 1)
    static let secondaryText = Color(red: 0.70, green: 0.79, blue: 0.90)
    static let accent = Color(red: 0.57, green: 0.76, blue: 1)
    static let gold = Color(red: 0.94, green: 0.79, blue: 0.48)
    static let divider = Color(red: 0.23, green: 0.34, blue: 0.48)
}

/// Decorative, static petals and light; no particles represent a person or measured data.
struct TwinAtmosphere: View {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    private var simplified: Bool { reduceTransparency || contrast == .increased }

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                RMTwinColors.background

                if !simplified {
                    LinearGradient(
                        colors: [Color(red: 0.045, green: 0.105, blue: 0.18),
                                 RMTwinColors.background,
                                 Color(red: 0.035, green: 0.075, blue: 0.14)],
                        startPoint: .topLeading, endPoint: .bottomTrailing
                    )
                    RadialGradient(
                        colors: [RMTwinColors.accent.opacity(0.11), .clear],
                        center: UnitPoint(x: 0.50, y: 0.25), startRadius: 4,
                        endRadius: max(geometry.size.width * 0.82, 1)
                    )
                    flecks
                }
            }
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
        .allowsHitTesting(false)
    }

    private var flecks: some View {
        Canvas { context, size in
            // Fixed coordinates keep every redraw, screenshot, and return visit stable.
            for index in 0..<28 {
                let x = CGFloat((index * 37 + 11) % 101) / 100
                let y = CGFloat((index * 53 + 7) % 103) / 102
                let width = CGFloat(2 + index % 4)
                let height = width * (index.isMultiple(of: 3) ? 1.8 : 0.7)
                let opacity = 0.10 + Double(index % 4) * 0.035
                let point = CGPoint(x: size.width * x, y: size.height * y)
                var petalContext = context
                petalContext.translateBy(x: point.x, y: point.y)
                petalContext.rotate(by: .degrees(Double((index * 47) % 180)))
                let rect = CGRect(x: -width / 2, y: -height / 2, width: width, height: height)
                petalContext.fill(Path(ellipseIn: rect), with: .color(RMTwinColors.accent.opacity(opacity)))

                if index.isMultiple(of: 4) {
                    var glowContext = context
                    glowContext.addFilter(.blur(radius: 4))
                    let glow = CGRect(x: point.x - 5, y: point.y - 5, width: 10, height: 10)
                    glowContext.fill(Path(ellipseIn: glow), with: .color(RMTwinColors.accent.opacity(0.08)))
                }
            }
        }
    }
}

/// Motion follows a measured amplitude envelope. Angular variation is decoration, not a spectrum.
enum RMTwinAudioMotion {
    static let frameInterval = 1.0 / 24.0
    static let silenceThreshold = 0.002

    static func level(_ value: Double?) -> Double {
        guard let value, value.isFinite else { return 0 }
        return min(1, max(0, value))
    }

    static func envelope(previous: Double, target: Double, elapsed: Double) -> Double {
        let current = level(previous)
        let measured = level(target)
        let destination = measured > silenceThreshold ? measured : 0
        guard elapsed.isFinite, elapsed > 0 else { return current }
        let duration = destination > current ? 0.055 : 0.16
        let response = 1 - exp(-min(elapsed, 0.25) / duration)
        let next = current + (destination - current) * response
        return destination == 0 && next < silenceThreshold ? 0 : next
    }

    /// Length as a fraction of the allocated square; the longest ray stays inside its edge.
    static func rayLength(index: Int, count: Int = 112, amplitude: Double) -> Double {
        let energy = level(amplitude)
        guard count > 0, index >= 0, energy > silenceThreshold else { return 0 }
        let angle = Double(index % count) / Double(count) * .pi * 2
        let broad = 0.5 + 0.5 * sin(angle * 7 + energy * 6.8)
        let detail = pow(sin(angle * 13 - energy * 4), 2)
        let weight = 0.24 + 0.76 * broad * (0.67 + 0.33 * detail)
        return 0.007 + pow(energy, 0.72) * 0.078 * weight
    }

    static func runs(reduceMotion: Bool, animationsDisabled: Bool, sceneActive: Bool,
                     visible: Bool, state: RMFlowerState, target: Double, envelope: Double) -> Bool {
        !reduceMotion && !animationsDisabled && sceneActive && visible
            && [.listening, .speaking].contains(state)
            && (level(target) > silenceThreshold || level(envelope) > 0)
    }
}

/// A measured-audio halo around the Twin flower; gold marks an original recording.
struct TwinPresence: View {
    var state: RMFlowerState = .idle
    var size: CGFloat = 116
    var original: Bool = false
    var audioLevel: Double? = nil

    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.rmAnimationsDisabled) private var animationsDisabled
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    @State private var visible = false
    @State private var targetLevel = 0.0
    @State private var smoothedLevel = 0.0

    private var tint: Color { original ? RMTwinColors.gold : RMTwinColors.accent }
    private var simplified: Bool { reduceTransparency || contrast == .increased }
    private var canReact: Bool {
        visible && scenePhase == .active && [.listening, .speaking].contains(state)
    }
    private var motionActive: Bool {
        RMTwinAudioMotion.runs(reduceMotion: reduceMotion, animationsDisabled: animationsDisabled,
                              sceneActive: scenePhase == .active, visible: visible, state: state,
                              target: targetLevel, envelope: smoothedLevel)
    }
    private var amplitude: Double { canReact && !reduceMotion && !animationsDisabled ? smoothedLevel : 0 }
    private var staticAudioActive: Bool { canReact && RMTwinAudioMotion.level(audioLevel) > RMTwinAudioMotion.silenceThreshold }

    var body: some View {
        ZStack {
            if !simplified {
                Circle()
                    .fill(RadialGradient(colors: [tint.opacity(0.10 + amplitude * 0.16),
                                                 tint.opacity(0.025 + amplitude * 0.045), .clear],
                                         center: .center, startRadius: size * 0.15, endRadius: size * 0.49))
                Circle()
                    .stroke(tint.opacity(0.16 + amplitude * 0.27), lineWidth: 2 + amplitude * 2)
                    .frame(width: size * 0.78, height: size * 0.78)
                    .blur(radius: 3 + amplitude * 3)
            }

            Circle()
                .strokeBorder(simplified ? tint : tint.opacity(0.42 + amplitude * 0.4),
                              lineWidth: contrast == .increased || ((reduceMotion || animationsDisabled) && staticAudioActive) ? 1.5 : 0.8)
                .frame(width: size * 0.78, height: size * 0.78)

            if amplitude > RMTwinAudioMotion.silenceThreshold {
                audioRays
            }

            // This flower shares the same measured envelope and has no idle animation clock.
            ForgetMeNotFlower(size: size * 0.60, phase: 0, amplitude: amplitude, state: state)
                .scaleEffect(1 + amplitude * 0.055)
                .shadow(color: simplified ? .clear : tint.opacity(0.20 + amplitude * 0.23),
                        radius: 8 + amplitude * 7)
        }
        .frame(width: size, height: size)
        .transaction { $0.animation = nil }
        .accessibilityHidden(true)
        .allowsHitTesting(false)
        .onAppear { visible = true; synchronizeInput() }
        .onDisappear { visible = false; targetLevel = 0; smoothedLevel = 0 }
        .onChange(of: audioLevel) { _, _ in synchronizeInput() }
        .onChange(of: state) { _, _ in synchronizeInput() }
        .onChange(of: scenePhase) { _, _ in synchronizeInput() }
        .onChange(of: reduceMotion) { _, _ in synchronizeInput() }
        .onChange(of: animationsDisabled) { _, _ in synchronizeInput() }
        .task(id: motionActive) {
            guard motionActive else { return }
            var lastTick = Date().timeIntervalSinceReferenceDate - RMTwinAudioMotion.frameInterval
            while !Task.isCancelled {
                let now = Date().timeIntervalSinceReferenceDate
                smoothedLevel = RMTwinAudioMotion.envelope(previous: smoothedLevel, target: targetLevel,
                                                            elapsed: now - lastTick)
                lastTick = now
                if targetLevel <= RMTwinAudioMotion.silenceThreshold && smoothedLevel == 0 { return }
                do {
                    try await Task.sleep(for: .seconds(RMTwinAudioMotion.frameInterval))
                } catch { return }
            }
        }
    }

    private func synchronizeInput() {
        targetLevel = canReact ? RMTwinAudioMotion.level(audioLevel) : 0
        if !canReact || reduceMotion || animationsDisabled { smoothedLevel = 0 }
    }

    private var audioRays: some View {
        Canvas { context, canvasSize in
            let side = min(canvasSize.width, canvasSize.height)
            let center = CGPoint(x: canvasSize.width / 2, y: canvasSize.height / 2)
            let radius = side * 0.397
            var rays = Path()
            for index in 0..<112 {
                let angle = Double(index) / 112 * .pi * 2 - .pi / 2
                let length = side * RMTwinAudioMotion.rayLength(index: index, amplitude: amplitude)
                let x = cos(angle), y = sin(angle)
                rays.move(to: CGPoint(x: center.x + x * radius, y: center.y + y * radius))
                rays.addLine(to: CGPoint(x: center.x + x * (radius + length), y: center.y + y * (radius + length)))
            }
            let stroke = StrokeStyle(lineWidth: max(0.65, side * 0.006), lineCap: .round)
            if !simplified {
                var glow = context
                glow.addFilter(.blur(radius: 2.3))
                glow.stroke(rays, with: .color(tint.opacity(amplitude * 0.36)), style: stroke)
            }
            context.stroke(rays, with: .color(simplified ? tint : tint.opacity(0.53 + amplitude * 0.44)), style: stroke)
        }
    }
}

private struct TwinGlassModifier: ViewModifier {
    var cornerRadius: CGFloat
    var original: Bool
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    private var simplified: Bool { reduceTransparency || contrast == .increased }
    private var tint: Color { original ? RMTwinColors.gold : RMTwinColors.accent }

    func body(content: Content) -> some View {
        content
            .background {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(simplified ? RMTwinColors.surface : RMTwinColors.surface.opacity(0.94))
                    .overlay {
                        if !simplified {
                            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                                .fill(LinearGradient(colors: [tint.opacity(0.055), .clear],
                                                     startPoint: .topLeading, endPoint: .bottomTrailing))
                        }
                    }
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
            .overlay {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .strokeBorder(tint.opacity(contrast == .increased ? 0.72 : 0.20),
                                  lineWidth: contrast == .increased ? 1.5 : 0.75)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
            .shadow(color: simplified ? .clear : .black.opacity(0.12), radius: 12, y: 5)
    }
}

extension View {
    /// Adds decoration only; callers retain control over their content padding.
    func twinGlass(cornerRadius: CGFloat = 18, original: Bool = false) -> some View {
        modifier(TwinGlassModifier(cornerRadius: cornerRadius, original: original))
    }
}
