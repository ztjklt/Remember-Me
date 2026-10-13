import SwiftUI

enum BrandTreatment { case automatic, material, flat, monochrome }

/// Import mark-material-1024.png into an Image Set and pass that asset's name.
/// This is a static brand image, never a microphone or processing indicator.
struct RememberMeBrand: View {
    var size: CGFloat = 48
    var treatment: BrandTreatment = .automatic
    var darkBackground = false
    var materialAsset: String? = nil
    var bundle: Bundle? = nil
    var monochromeColor: Color = .primary
    var label: String? = nil

    private var dimension: CGFloat { max(16, size) }
    private var useMaterial: Bool {
        materialAsset != nil && (treatment == .material || (treatment == .automatic && dimension >= 64))
    }
    var body: some View {
        Group {
            if useMaterial, let asset = materialAsset {
                Image(asset, bundle: bundle).resizable().scaledToFit()
            } else {
                Canvas { context, canvas in
                    let mono = treatment == .monochrome
                    let blue = darkBackground ? Color(red: 174/255, green: 196/255, blue: 1) : Color(red: 50/255, green: 92/255, blue: 203/255)
                    var petal = Path()
                    petal.move(to: CGPoint(x: 128, y: 125))
                    petal.addCurve(to: CGPoint(x: 88, y: 71), control1: CGPoint(x: 111, y: 119), control2: CGPoint(x: 91, y: 96))
                    petal.addCurve(to: CGPoint(x: 122, y: 22), control1: CGPoint(x: 85, y: 45), control2: CGPoint(x: 98, y: 23))
                    petal.addCurve(to: CGPoint(x: 166, y: 70), control1: CGPoint(x: 148, y: 20), control2: CGPoint(x: 168, y: 43))
                    petal.addCurve(to: CGPoint(x: 132, y: 125), control1: CGPoint(x: 164, y: 94), control2: CGPoint(x: 145, y: 118))
                    petal.closeSubpath()
                    context.scaleBy(x: canvas.width / 256, y: canvas.height / 256)
                    for i in 0..<5 {
                        var layer = context
                        layer.translateBy(x: 128, y: 128)
                        layer.rotate(by: .degrees(Double(i) * 72))
                        layer.translateBy(x: -128, y: -128)
                        layer.fill(petal, with: .color(mono ? monochromeColor : blue))
                    }
                    let r: CGFloat = mono ? 9 : 12
                    let heart = Path(ellipseIn: CGRect(x: 128-r, y: 128-r, width: 2*r, height: 2*r))
                    context.fill(heart, with: .color(mono ? monochromeColor : Color(red: 233/255, green: 184/255, blue: 91/255)))
                }
            }
        }
        .frame(width: dimension, height: dimension)
        .accessibilityLabel(Text(label ?? ""))
        .accessibilityHidden(label == nil)
    }
}
