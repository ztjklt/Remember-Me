import SwiftUI
import UIKit

enum RMColors {
    private static func adaptive(_ light: UInt32, _ dark: UInt32) -> Color {
        Color(uiColor: UIColor { traits in
            let hex = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat((hex >> 16) & 255) / 255,
                           green: CGFloat((hex >> 8) & 255) / 255,
                           blue: CGFloat(hex & 255) / 255, alpha: 1)
        })
    }
    // Shared blue/white palette; dark appearance keeps the same blue hierarchy.
    static let background = adaptive(0xF5F9FF, 0x0C192D)
    static let surface = adaptive(0xFFFFFF, 0x142640)
    static let subtle = adaptive(0xEAF3FF, 0x1C3453)
    static let text = adaptive(0x142C4D, 0xF0F6FF)
    static let secondaryText = adaptive(0x526681, 0xB1C5DF)
    static let action = adaptive(0x2563EB, 0x9CC3FF)
    static let brand = adaptive(0x5B9BF3, 0x79B0FF)
    // Botanical colors stay independent of the blue/white interface palette.
    static let flowerPetal = adaptive(0x7B9CE8, 0x91ADEB)
    static let petalLight = adaptive(0xB3C9F5, 0xB0C6F4)
    static let floralSurface = adaptive(0xEAF3FF, 0x203D64)
    static let artworkTint = adaptive(0xA7CAFF, 0xBBD8FF)
    static let flowerCenter = adaptive(0xF3D88C, 0xEBD088)
    static let flowerEye = adaptive(0xFFFDF6, 0xFFFDF6)
    static let flowerStem = adaptive(0x819F8C, 0x91AC9C)
    static let flowerMark = adaptive(0x325CCB, 0xAEC4FF)
    static let flowerMarkCenter = adaptive(0xE9B85B, 0xE9B85B)
    static let flowerGlyph = adaptive(0x567AC3, 0xA3BCEB)
    static let stem = adaptive(0x7699C4, 0x8FB6E5)
    static let divider = adaptive(0xD6E5F5, 0x355274)
    static let onAction = adaptive(0xFFFFFF, 0x10284A)
    static let danger = adaptive(0xA84150, 0xF199A5)
    static let onDanger = adaptive(0xFFFFFF, 0x202638)
    static let success = adaptive(0x426D5C, 0xA5CCB8)
    static let shadow = adaptive(0x142C4D, 0x000B1D).opacity(0.08)
}

enum RMTypography {
    static let display = Font.system(.largeTitle, design: .rounded).weight(.medium)
    static let title = Font.system(.title2).weight(.medium)
    static let heading = Font.system(.headline).weight(.medium)
    static let body = Font.system(.body)
    static let detail = Font.system(.subheadline)
    static let caption = Font.system(.caption)
    static let timer = Font.system(.largeTitle, design: .rounded).monospacedDigit()
}

enum RMSpacing {
    static let xxs: CGFloat = 4
    static let xs: CGFloat = 8
    static let sm: CGFloat = 12
    static let md: CGFloat = 16
    static let lg: CGFloat = 24
    static let xl: CGFloat = 32
    static let xxl: CGFloat = 48
    static let page: CGFloat = 20
}

enum RMRadius {
    static let card: CGFloat = 8
    static let control: CGFloat = 12
    static let message: CGFloat = 16
}

enum RMMetrics {
    static let touchTarget: CGFloat = 44
    static let buttonHeight: CGFloat = 52
    static let controlDiameter: CGFloat = 56
    static let icon: CGFloat = 20
    static let heroFlower: CGFloat = 132
    static let recordingFlower: CGFloat = 156
    static let inlineFlower: CGFloat = 32
    static let emptyFlower: CGFloat = 72
    static let editorHeight: CGFloat = 180
    static let sampleEditorHeight: CGFloat = 112
    static let maximumReadingWidth: CGFloat = 600
    static let waveformHeight: CGFloat = 64
}

enum RMShadow {
    static let radius: CGFloat = 8
    static let offset: CGFloat = 3
}

enum RMGradients {
    static let petal = LinearGradient(colors: [RMColors.petalLight, RMColors.flowerPetal],
                                     startPoint: .topLeading, endPoint: .bottomTrailing)
    static let center = LinearGradient(colors: [RMColors.flowerCenter, RMColors.flowerCenter.opacity(0.8)],
                                      startPoint: .top, endPoint: .bottom)
}

enum RMAnimationTokens {
    static let press = Animation.easeOut(duration: 0.14)
    static let transition = Animation.easeInOut(duration: 0.25)
    static let audioSmoothing = Animation.easeOut(duration: 0.22)
    static let frameInterval: TimeInterval = 1 / 24
    static let breathDuration: TimeInterval = 6.8
    static let breathingAmplitude: Double = 0.012
}

private struct RMAnimationsDisabledKey: EnvironmentKey {
    static let defaultValue = false
}

extension EnvironmentValues {
    var rmAnimationsDisabled: Bool {
        get { self[RMAnimationsDisabledKey.self] }
        set { self[RMAnimationsDisabledKey.self] = newValue }
    }
}
