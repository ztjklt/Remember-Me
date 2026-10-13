"""Generate the same silhouettes for Compose and SwiftUI; run after build.py."""
from pathlib import Path
import argparse,re
from build import ICONS
ROOT=Path(__file__).resolve().parent
args=argparse.ArgumentParser();args.add_argument('--ios-root',type=Path);a=args.parse_args()
repo=ROOT.parents[2]
kt='''package me.remember.app.core.designsystem

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.*
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.*

enum class MemoryGlyphKind { Voice, Archive, Memory, Quote, Review, Recall }

/** Generated silhouettes; decorative by default. Small sizes omit shadows and back layers. */
@Composable fun MemoryGlyph(kind: MemoryGlyphKind, size: Dp = 96.dp, label: String? = null) {
    val dark = MaterialTheme.colorScheme.background.luminance() < .5f
    val ink = if(dark) Color(0xFFD0DFFA) else Color(0xFF385590)
    val paper = if(dark) Color(0xFF536C99) else Color(0xFFEDF2FB)
    val end = if(dark) Color(0xFF334565) else Color(0xFFCBD7EE)
    val back = if(dark) Color(0xFF354866) else Color(0xFFA4B9DF)
    val blue = if(dark) Color(0xFFA3BCEB) else Color(0xFF567AC3)
    val gold = if(dark) Color(0xFFD4B06F) else Color(0xFFC39A4B)
    val light = if(dark) Color(0xFF253956) else Color(0xFFF6F8FC)
    val dimension=size.coerceIn(16.dp,192.dp)
    val flat=dimension<=32.dp
    val material=dimension>=64.dp
    val shapes=remember(kind) { when(kind) {
'''
for name,(_,_,paths) in ICONS.items():
 kt+=f'        MemoryGlyphKind.{name.title()} -> listOf(\n'+',\n'.join(f'            "{role}" to PathParser().parsePathString("{d}").toPath()' for role,d in paths)+'\n        )\n'
kt+='''    } }
    Canvas(Modifier.size(dimension).clearAndSetSemantics { if(label!=null) contentDescription=label }) {
        scale(this.size.width/96f,this.size.height/96f,pivot=Offset.Zero) {
            shapes.forEach { (role,path) ->
                if(!(flat&&role=="back")) {
                    val line=flat||role=="line"||role=="lightline"
                    if(material&&(role=="paper"||role=="blue")) {
                        for(offset in listOf(1.5f,2.5f,3.5f)) translate(0f,offset) {
                            drawPath(path,Color(0xFF142D55).copy(alpha=.045f))
                        }
                    }
                    when {
                        line -> drawPath(path,if(flat||role=="line")ink else light,style=Stroke(if(flat)6f else 3f,cap=StrokeCap.Round,join=StrokeJoin.Round))
                        role=="paper"&&material -> drawPath(path,Brush.linearGradient(listOf(paper,end),end=Offset(77f,96f)))
                        else -> drawPath(path,when(role){"paper"->paper;"back"->back.copy(alpha=.8f);"blue"->blue;"gold"->gold;else->ink})
                    }
                    if(material&&role=="paper") clipPath(path) {
                        drawPath(path,light.copy(alpha=.55f),style=Stroke(1.5f))
                    }
                }
            }
        }
    }
}
'''
(repo/'apps/android/app/src/main/java/me/remember/app/core/designsystem/MemoryGlyph.kt').write_text(kt,encoding='utf-8')

def swift_path(d):
 tokens=re.findall(r'[MLHVQCZ]|-?\d+(?:\.\d+)?',d);i=0;x=y=0;out=['var p=Path()']
 def pt(x,y):return f'CGPoint(x:{x},y:{y})'
 while i<len(tokens):
  command=tokens[i];i+=1;n={'M':2,'L':2,'H':1,'V':1,'Q':4,'C':6,'Z':0}[command];v=tokens[i:i+n];i+=n
  if command in ('M','L'):
   x,y=v;out.append(f'p.{"move" if command=="M" else "addLine"}(to:{pt(x,y)})')
  elif command in ('H','V'):
   if command=='H':x=v[0]
   else:y=v[0]
   out.append(f'p.addLine(to:{pt(x,y)})')
  elif command=='Q':
   x,y=v[2:];out.append(f'p.addQuadCurve(to:{pt(x,y)},control:{pt(v[0],v[1])})')
  elif command=='C':
   x,y=v[4:];out.append(f'p.addCurve(to:{pt(x,y)},control1:{pt(v[0],v[1])},control2:{pt(v[2],v[3])})')
  else:out.append('p.closeSubpath()')
 return '{ '+';'.join(out)+';return p }()'
swift='''// BEGIN GENERATED MEMORY GLYPHS
private enum MemoryGlyphKind { case voice, archive, memory, quote, review, recall }
private struct MemoryGlyph: View {
    let kind: MemoryGlyphKind
    var size: CGFloat = 96
    var label: String? = nil
    @Environment(\\.colorScheme) private var scheme
    @Environment(\\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\\.colorSchemeContrast) private var contrast
    private func color(_ day: UInt32,_ night: UInt32) -> Color {
        let v=scheme == .dark ? night : day
        return Color(red:Double((v>>16)&255)/255,green:Double((v>>8)&255)/255,blue:Double(v&255)/255)
    }
    private var shapes: [(String,Path)] {
        switch kind {
'''
for name,(_,_,paths) in ICONS.items():
 swift+=f'        case .{name}: return [\n'+',\n'.join(f'            ("{role}",{swift_path(d)})' for role,d in paths)+'\n        ]\n'
swift+='''        }
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
'''
(ROOT/'MemoryGlyph.swift').write_text('import SwiftUI\n\n'+swift,encoding='utf-8')
if a.ios_root:
 file=a.ios_root/'apps/ios/RememberMe/Views.swift';text=file.read_text(encoding='utf-8')
 if '// BEGIN GENERATED MEMORY GLYPHS' in text: text=re.sub(r'// BEGIN GENERATED MEMORY GLYPHS.*?// END GENERATED MEMORY GLYPHS\n',lambda _:swift,text,flags=re.S)
 else:text+='\n'+swift
 file.write_text(text,encoding='utf-8')
