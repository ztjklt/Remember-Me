import SwiftUI

// BEGIN GENERATED MEMORY GLYPHS
private enum MemoryGlyphKind { case voice, archive, memory, quote, review, recall }
private struct MemoryGlyph: View {
    let kind: MemoryGlyphKind
    var size: CGFloat = 96
    var label: String? = nil
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    private func color(_ day: UInt32,_ night: UInt32) -> Color {
        let v=scheme == .dark ? night : day
        return Color(red:Double((v>>16)&255)/255,green:Double((v>>8)&255)/255,blue:Double(v&255)/255)
    }
    private var shapes: [(String,Path)] {
        switch kind {
        case .voice: return [
            ("back",{ var p=Path();p.move(to:CGPoint(x:31,y:18));p.addQuadCurve(to:CGPoint(x:39,y:10),control:CGPoint(x:31,y:10));p.addLine(to:CGPoint(x:65,y:10));p.addQuadCurve(to:CGPoint(x:73,y:18),control:CGPoint(x:73,y:10));p.addLine(to:CGPoint(x:73,y:68));p.addQuadCurve(to:CGPoint(x:65,y:76),control:CGPoint(x:73,y:76));p.addLine(to:CGPoint(x:39,y:76));p.addQuadCurve(to:CGPoint(x:31,y:68),control:CGPoint(x:31,y:76));p.closeSubpath();return p }()),
            ("paper",{ var p=Path();p.move(to:CGPoint(x:21,y:28));p.addQuadCurve(to:CGPoint(x:29,y:20),control:CGPoint(x:21,y:20));p.addLine(to:CGPoint(x:57,y:20));p.addQuadCurve(to:CGPoint(x:65,y:28),control:CGPoint(x:65,y:20));p.addLine(to:CGPoint(x:65,y:78));p.addQuadCurve(to:CGPoint(x:57,y:86),control:CGPoint(x:65,y:86));p.addLine(to:CGPoint(x:29,y:86));p.addQuadCurve(to:CGPoint(x:21,y:78),control:CGPoint(x:21,y:86));p.closeSubpath();return p }()),
            ("line",{ var p=Path();p.move(to:CGPoint(x:31,y:49));p.addLine(to:CGPoint(x:31,y:61));p.move(to:CGPoint(x:39,y:39));p.addLine(to:CGPoint(x:39,y:70));p.move(to:CGPoint(x:47,y:44));p.addLine(to:CGPoint(x:47,y:65));p.move(to:CGPoint(x:55,y:51));p.addLine(to:CGPoint(x:55,y:59));return p }()),
            ("gold",{ var p=Path();p.move(to:CGPoint(x:62,y:20));p.addCurve(to:CGPoint(x:77,y:16),control1:CGPoint(x:62,y:13),control2:CGPoint(x:72,y:11));p.addCurve(to:CGPoint(x:62,y:20),control1:CGPoint(x:75,y:23),control2:CGPoint(x:67,y:25));p.closeSubpath();return p }())
        ]
        case .archive: return [
            ("back",{ var p=Path();p.move(to:CGPoint(x:23,y:14));p.addQuadCurve(to:CGPoint(x:29,y:8),control:CGPoint(x:23,y:8));p.addLine(to:CGPoint(x:70,y:8));p.addQuadCurve(to:CGPoint(x:76,y:14),control:CGPoint(x:76,y:8));p.addLine(to:CGPoint(x:76,y:65));p.addQuadCurve(to:CGPoint(x:70,y:71),control:CGPoint(x:76,y:71));p.addLine(to:CGPoint(x:29,y:71));p.addQuadCurve(to:CGPoint(x:23,y:65),control:CGPoint(x:23,y:71));p.closeSubpath();return p }()),
            ("paper",{ var p=Path();p.move(to:CGPoint(x:14,y:29));p.addQuadCurve(to:CGPoint(x:21,y:22),control:CGPoint(x:14,y:22));p.addLine(to:CGPoint(x:64,y:22));p.addQuadCurve(to:CGPoint(x:71,y:29),control:CGPoint(x:71,y:22));p.addLine(to:CGPoint(x:71,y:80));p.addQuadCurve(to:CGPoint(x:64,y:87),control:CGPoint(x:71,y:87));p.addLine(to:CGPoint(x:21,y:87));p.addQuadCurve(to:CGPoint(x:14,y:80),control:CGPoint(x:14,y:87));p.closeSubpath();return p }()),
            ("line",{ var p=Path();p.move(to:CGPoint(x:26,y:38));p.addLine(to:CGPoint(x:57,y:38));p.move(to:CGPoint(x:26,y:48));p.addLine(to:CGPoint(x:48,y:48));p.move(to:CGPoint(x:26,y:63));p.addCurve(to:CGPoint(x:57,y:60),control1:CGPoint(x:36,y:53),control2:CGPoint(x:44,y:74));p.move(to:CGPoint(x:26,y:75));p.addLine(to:CGPoint(x:40,y:75));return p }()),
            ("gold",{ var p=Path();p.move(to:CGPoint(x:61,y:12));p.addLine(to:CGPoint(x:69,y:12));p.addLine(to:CGPoint(x:69,y:35));p.addLine(to:CGPoint(x:65,y:31));p.addLine(to:CGPoint(x:61,y:35));p.closeSubpath();return p }())
        ]
        case .memory: return [
            ("back",{ var p=Path();p.move(to:CGPoint(x:30,y:16));p.addLine(to:CGPoint(x:70,y:11));p.addQuadCurve(to:CGPoint(x:77,y:18),control:CGPoint(x:76,y:11));p.addLine(to:CGPoint(x:84,y:69));p.addQuadCurve(to:CGPoint(x:79,y:76),control:CGPoint(x:85,y:75));p.addLine(to:CGPoint(x:39,y:81));p.closeSubpath();return p }()),
            ("paper",{ var p=Path();p.move(to:CGPoint(x:14,y:20));p.addQuadCurve(to:CGPoint(x:21,y:13),control:CGPoint(x:14,y:13));p.addLine(to:CGPoint(x:61,y:13));p.addQuadCurve(to:CGPoint(x:68,y:20),control:CGPoint(x:68,y:13));p.addLine(to:CGPoint(x:68,y:79));p.addQuadCurve(to:CGPoint(x:61,y:86),control:CGPoint(x:68,y:86));p.addLine(to:CGPoint(x:21,y:86));p.addQuadCurve(to:CGPoint(x:14,y:79),control:CGPoint(x:14,y:86));p.closeSubpath();return p }()),
            ("line",{ var p=Path();p.move(to:CGPoint(x:39,y:66));p.addCurve(to:CGPoint(x:48,y:40),control1:CGPoint(x:43,y:57),control2:CGPoint(x:47,y:49));p.move(to:CGPoint(x:42,y:61));p.addQuadCurve(to:CGPoint(x:30,y:54),control:CGPoint(x:32,y:61));p.addQuadCurve(to:CGPoint(x:43,y:58),control:CGPoint(x:39,y:52));p.move(to:CGPoint(x:45,y:53));p.addQuadCurve(to:CGPoint(x:57,y:46),control:CGPoint(x:55,y:52));return p }()),
            ("blue",{ var p=Path();p.move(to:CGPoint(x:46,y:39));p.addCurve(to:CGPoint(x:39,y:25),control1:CGPoint(x:29,y:40),control2:CGPoint(x:29,y:24));p.addCurve(to:CGPoint(x:52,y:27),control1:CGPoint(x:39,y:14),control2:CGPoint(x:54,y:16));p.addCurve(to:CGPoint(x:57,y:41),control1:CGPoint(x:62,y:22),control2:CGPoint(x:70,y:37));p.addCurve(to:CGPoint(x:47,y:48),control1:CGPoint(x:66,y:51),control2:CGPoint(x:50,y:60));p.addCurve(to:CGPoint(x:46,y:39),control1:CGPoint(x:36,y:56),control2:CGPoint(x:29,y:41));p.closeSubpath();return p }()),
            ("gold",{ var p=Path();p.move(to:CGPoint(x:52,y:38));p.addCurve(to:CGPoint(x:44,y:38),control1:CGPoint(x:52,y:43),control2:CGPoint(x:44,y:43));p.addCurve(to:CGPoint(x:52,y:38),control1:CGPoint(x:44,y:33),control2:CGPoint(x:52,y:33));p.closeSubpath();return p }())
        ]
        case .quote: return [
            ("back",{ var p=Path();p.move(to:CGPoint(x:24,y:13));p.addLine(to:CGPoint(x:77,y:13));p.addQuadCurve(to:CGPoint(x:84,y:20),control:CGPoint(x:84,y:13));p.addLine(to:CGPoint(x:84,y:61));p.addQuadCurve(to:CGPoint(x:77,y:68),control:CGPoint(x:84,y:68));p.addLine(to:CGPoint(x:62,y:68));p.addLine(to:CGPoint(x:51,y:79));p.addLine(to:CGPoint(x:51,y:68));p.addLine(to:CGPoint(x:24,y:68));p.addQuadCurve(to:CGPoint(x:17,y:61),control:CGPoint(x:17,y:68));p.addLine(to:CGPoint(x:17,y:20));p.addQuadCurve(to:CGPoint(x:24,y:13),control:CGPoint(x:17,y:13));p.closeSubpath();return p }()),
            ("paper",{ var p=Path();p.move(to:CGPoint(x:15,y:25));p.addLine(to:CGPoint(x:65,y:25));p.addQuadCurve(to:CGPoint(x:73,y:33),control:CGPoint(x:73,y:25));p.addLine(to:CGPoint(x:73,y:71));p.addQuadCurve(to:CGPoint(x:65,y:79),control:CGPoint(x:73,y:79));p.addLine(to:CGPoint(x:34,y:79));p.addLine(to:CGPoint(x:21,y:87));p.addLine(to:CGPoint(x:21,y:79));p.addLine(to:CGPoint(x:15,y:79));p.addQuadCurve(to:CGPoint(x:8,y:71),control:CGPoint(x:8,y:79));p.addLine(to:CGPoint(x:8,y:33));p.addQuadCurve(to:CGPoint(x:15,y:25),control:CGPoint(x:8,y:25));p.closeSubpath();return p }()),
            ("line",{ var p=Path();p.move(to:CGPoint(x:23,y:43));p.addLine(to:CGPoint(x:34,y:43));p.addLine(to:CGPoint(x:34,y:54));p.addLine(to:CGPoint(x:23,y:54));p.closeSubpath();p.move(to:CGPoint(x:34,y:54));p.addQuadCurve(to:CGPoint(x:26,y:65),control:CGPoint(x:34,y:62));p.move(to:CGPoint(x:45,y:43));p.addLine(to:CGPoint(x:56,y:43));p.addLine(to:CGPoint(x:56,y:54));p.addLine(to:CGPoint(x:45,y:54));p.closeSubpath();p.move(to:CGPoint(x:56,y:54));p.addQuadCurve(to:CGPoint(x:48,y:65),control:CGPoint(x:56,y:62));return p }()),
            ("gold",{ var p=Path();p.move(to:CGPoint(x:68,y:14));p.addLine(to:CGPoint(x:77,y:14));p.addLine(to:CGPoint(x:77,y:32));p.addLine(to:CGPoint(x:72,y:28));p.addLine(to:CGPoint(x:68,y:32));p.closeSubpath();return p }())
        ]
        case .review: return [
            ("back",{ var p=Path();p.move(to:CGPoint(x:30,y:10));p.addLine(to:CGPoint(x:68,y:10));p.addQuadCurve(to:CGPoint(x:76,y:18),control:CGPoint(x:76,y:10));p.addLine(to:CGPoint(x:76,y:69));p.addQuadCurve(to:CGPoint(x:68,y:77),control:CGPoint(x:76,y:77));p.addLine(to:CGPoint(x:30,y:77));p.addQuadCurve(to:CGPoint(x:22,y:69),control:CGPoint(x:22,y:77));p.addLine(to:CGPoint(x:22,y:18));p.addQuadCurve(to:CGPoint(x:30,y:10),control:CGPoint(x:22,y:10));p.closeSubpath();return p }()),
            ("paper",{ var p=Path();p.move(to:CGPoint(x:19,y:23));p.addLine(to:CGPoint(x:57,y:23));p.addQuadCurve(to:CGPoint(x:65,y:31),control:CGPoint(x:65,y:23));p.addLine(to:CGPoint(x:65,y:79));p.addQuadCurve(to:CGPoint(x:57,y:87),control:CGPoint(x:65,y:87));p.addLine(to:CGPoint(x:19,y:87));p.addQuadCurve(to:CGPoint(x:11,y:79),control:CGPoint(x:11,y:87));p.addLine(to:CGPoint(x:11,y:31));p.addQuadCurve(to:CGPoint(x:19,y:23),control:CGPoint(x:11,y:23));p.closeSubpath();return p }()),
            ("line",{ var p=Path();p.move(to:CGPoint(x:24,y:39));p.addLine(to:CGPoint(x:51,y:39));p.move(to:CGPoint(x:24,y:50));p.addLine(to:CGPoint(x:43,y:50));p.move(to:CGPoint(x:24,y:62));p.addLine(to:CGPoint(x:37,y:62));return p }()),
            ("blue",{ var p=Path();p.move(to:CGPoint(x:62,y:50));p.addCurve(to:CGPoint(x:62,y:82),control1:CGPoint(x:88,y:50),control2:CGPoint(x:88,y:82));p.addCurve(to:CGPoint(x:62,y:50),control1:CGPoint(x:40,y:82),control2:CGPoint(x:40,y:50));p.closeSubpath();return p }()),
            ("lightline",{ var p=Path();p.move(to:CGPoint(x:55,y:66));p.addLine(to:CGPoint(x:61,y:72));p.addLine(to:CGPoint(x:72,y:60));return p }())
        ]
        case .recall: return [
            ("back",{ var p=Path();p.move(to:CGPoint(x:50,y:12));p.addCurve(to:CGPoint(x:66,y:81),control1:CGPoint(x:88,y:12),control2:CGPoint(x:94,y:67));p.addCurve(to:CGPoint(x:12,y:50),control1:CGPoint(x:43,y:95),control2:CGPoint(x:11,y:77));p.addCurve(to:CGPoint(x:50,y:12),control1:CGPoint(x:12,y:28),control2:CGPoint(x:29,y:12));p.closeSubpath();return p }()),
            ("paper",{ var p=Path();p.move(to:CGPoint(x:44,y:22));p.addCurve(to:CGPoint(x:61,y:75),control1:CGPoint(x:72,y:22),control2:CGPoint(x:84,y:62));p.addCurve(to:CGPoint(x:19,y:49),control1:CGPoint(x:39,y:89),control2:CGPoint(x:18,y:69));p.addCurve(to:CGPoint(x:44,y:22),control1:CGPoint(x:20,y:34),control2:CGPoint(x:29,y:22));p.closeSubpath();return p }()),
            ("line",{ var p=Path();p.move(to:CGPoint(x:31,y:47));p.addCurve(to:CGPoint(x:61,y:46),control1:CGPoint(x:33,y:30),control2:CGPoint(x:57,y:31));p.addCurve(to:CGPoint(x:32,y:59),control1:CGPoint(x:67,y:64),control2:CGPoint(x:41,y:74));p.move(to:CGPoint(x:31,y:35));p.addLine(to:CGPoint(x:31,y:47));p.addLine(to:CGPoint(x:42,y:47));p.move(to:CGPoint(x:45,y:44));p.addLine(to:CGPoint(x:45,y:54));p.addLine(to:CGPoint(x:53,y:59));return p }()),
            ("gold",{ var p=Path();p.move(to:CGPoint(x:71,y:19));p.addCurve(to:CGPoint(x:87,y:19),control1:CGPoint(x:72,y:10),control2:CGPoint(x:85,y:11));p.addCurve(to:CGPoint(x:71,y:19),control1:CGPoint(x:82,y:27),control2:CGPoint(x:74,y:27));p.closeSubpath();return p }())
        ]
        }
    }
    var body: some View {
        let dimension=min(192,max(16,size))
        let flat=dimension<=32 || reduceTransparency || contrast == .increased
        let material=dimension>=64 && !flat
        Canvas { context,canvas in
            context.scaleBy(x:canvas.width/96,y:canvas.height/96)
            let ink=color(0x385590,0xD0DFFA),paper=color(0xEDF2FB,0x536C99),end=color(0xCBD7EE,0x334565)
            for (role,path) in shapes where !(flat && role == "back") {
                if flat || role == "line" || role == "lightline" {
                    context.stroke(path,with:.color(flat || role == "line" ? ink : color(0xF6F8FC,0x253956)),style:StrokeStyle(lineWidth:flat ? 6 : 3,lineCap:.round,lineJoin:.round))
                } else {
                    var layer=context
                    if material && (role == "paper" || role == "blue") { layer.addFilter(.shadow(color:color(0x28426E,0x071326).opacity(0.2),radius:2.2,x:0,y:2.5)) }
                    if role == "paper" && material {
                        layer.fill(path,with:.linearGradient(Gradient(colors:[paper,end]),startPoint:.zero,endPoint:CGPoint(x:77,y:96)))
                    } else {
                        layer.fill(path,with:.color(role == "back" ? color(0xA4B9DF,0x354866).opacity(0.8) : role == "blue" ? color(0x567AC3,0xA3BCEB) : role == "gold" ? color(0xC39A4B,0xD4B06F) : paper))
                    }
                    if material && role == "paper" { var rim=context;rim.clip(to:path);rim.stroke(path,with:.color(color(0xF6F8FC,0x253956).opacity(0.55)),lineWidth:1.5) }
                }
            }
        }.frame(width:dimension,height:dimension).accessibilityLabel(Text(label ?? "")).accessibilityHidden(label == nil)
    }
}
// END GENERATED MEMORY GLYPHS
