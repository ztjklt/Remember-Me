package me.remember.app.core.designsystem

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
        MemoryGlyphKind.Voice -> listOf(
            "back" to PathParser().parsePathString("M31 18 Q31 10 39 10 H65 Q73 10 73 18 V68 Q73 76 65 76 H39 Q31 76 31 68 Z").toPath(),
            "paper" to PathParser().parsePathString("M21 28 Q21 20 29 20 H57 Q65 20 65 28 V78 Q65 86 57 86 H29 Q21 86 21 78 Z").toPath(),
            "line" to PathParser().parsePathString("M31 49 V61 M39 39 V70 M47 44 V65 M55 51 V59").toPath(),
            "gold" to PathParser().parsePathString("M62 20 C62 13 72 11 77 16 C75 23 67 25 62 20 Z").toPath()
        )
        MemoryGlyphKind.Archive -> listOf(
            "back" to PathParser().parsePathString("M23 14 Q23 8 29 8 H70 Q76 8 76 14 V65 Q76 71 70 71 H29 Q23 71 23 65 Z").toPath(),
            "paper" to PathParser().parsePathString("M14 29 Q14 22 21 22 H64 Q71 22 71 29 V80 Q71 87 64 87 H21 Q14 87 14 80 Z").toPath(),
            "line" to PathParser().parsePathString("M26 38 H57 M26 48 H48 M26 63 C36 53 44 74 57 60 M26 75 H40").toPath(),
            "gold" to PathParser().parsePathString("M61 12 H69 V35 L65 31 L61 35 Z").toPath()
        )
        MemoryGlyphKind.Memory -> listOf(
            "back" to PathParser().parsePathString("M30 16 L70 11 Q76 11 77 18 L84 69 Q85 75 79 76 L39 81 Z").toPath(),
            "paper" to PathParser().parsePathString("M14 20 Q14 13 21 13 H61 Q68 13 68 20 V79 Q68 86 61 86 H21 Q14 86 14 79 Z").toPath(),
            "line" to PathParser().parsePathString("M39 66 C43 57 47 49 48 40 M42 61 Q32 61 30 54 Q39 52 43 58 M45 53 Q55 52 57 46").toPath(),
            "blue" to PathParser().parsePathString("M46 39 C29 40 29 24 39 25 C39 14 54 16 52 27 C62 22 70 37 57 41 C66 51 50 60 47 48 C36 56 29 41 46 39 Z").toPath(),
            "gold" to PathParser().parsePathString("M52 38 C52 43 44 43 44 38 C44 33 52 33 52 38 Z").toPath()
        )
        MemoryGlyphKind.Quote -> listOf(
            "back" to PathParser().parsePathString("M24 13 H77 Q84 13 84 20 V61 Q84 68 77 68 H62 L51 79 V68 H24 Q17 68 17 61 V20 Q17 13 24 13 Z").toPath(),
            "paper" to PathParser().parsePathString("M15 25 H65 Q73 25 73 33 V71 Q73 79 65 79 H34 L21 87 V79 H15 Q8 79 8 71 V33 Q8 25 15 25 Z").toPath(),
            "line" to PathParser().parsePathString("M23 43 H34 V54 H23 Z M34 54 Q34 62 26 65 M45 43 H56 V54 H45 Z M56 54 Q56 62 48 65").toPath(),
            "gold" to PathParser().parsePathString("M68 14 H77 V32 L72 28 L68 32 Z").toPath()
        )
        MemoryGlyphKind.Review -> listOf(
            "back" to PathParser().parsePathString("M30 10 H68 Q76 10 76 18 V69 Q76 77 68 77 H30 Q22 77 22 69 V18 Q22 10 30 10 Z").toPath(),
            "paper" to PathParser().parsePathString("M19 23 H57 Q65 23 65 31 V79 Q65 87 57 87 H19 Q11 87 11 79 V31 Q11 23 19 23 Z").toPath(),
            "line" to PathParser().parsePathString("M24 39 H51 M24 50 H43 M24 62 H37").toPath(),
            "blue" to PathParser().parsePathString("M62 50 C88 50 88 82 62 82 C40 82 40 50 62 50 Z").toPath(),
            "lightline" to PathParser().parsePathString("M55 66 L61 72 L72 60").toPath()
        )
        MemoryGlyphKind.Recall -> listOf(
            "back" to PathParser().parsePathString("M50 12 C88 12 94 67 66 81 C43 95 11 77 12 50 C12 28 29 12 50 12 Z").toPath(),
            "paper" to PathParser().parsePathString("M44 22 C72 22 84 62 61 75 C39 89 18 69 19 49 C20 34 29 22 44 22 Z").toPath(),
            "line" to PathParser().parsePathString("M31 47 C33 30 57 31 61 46 C67 64 41 74 32 59 M31 35 V47 H42 M45 44 V54 L53 59").toPath(),
            "gold" to PathParser().parsePathString("M71 19 C72 10 85 11 87 19 C82 27 74 27 71 19 Z").toPath()
        )
    } }
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
