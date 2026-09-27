package me.remember.app.core.designsystem

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

enum class BrandTreatment { Auto, Material, Flat, Monochrome }

/** Static brand asset. Supply the exported PNG painter for the material treatment. */
@Composable
fun RememberMeBrand(
    modifier: Modifier = Modifier,
    size: Dp = 48.dp,
    treatment: BrandTreatment = BrandTreatment.Auto,
    darkBackground: Boolean = isSystemInDarkTheme(),
    materialPainter: Painter? = null,
    monochromeColor: Color = if(darkBackground) Color(0xFFEDF2FF) else Color(0xFF17243B),
    label: String? = null,
) {
    val dimension = size.coerceAtLeast(16.dp)
    val useMaterial = materialPainter != null &&
        (treatment == BrandTreatment.Material || (treatment == BrandTreatment.Auto && dimension >= 64.dp))
    if(useMaterial) {
        Image(painter=materialPainter!!,contentDescription=label,modifier=modifier.size(dimension))
        return
    }
    val petal=remember { Path().apply {
        moveTo(128f,125f)
        cubicTo(111f,119f,91f,96f,88f,71f)
        cubicTo(85f,45f,98f,23f,122f,22f)
        cubicTo(148f,20f,168f,43f,166f,70f)
        cubicTo(164f,94f,145f,118f,132f,125f)
        close()
    } }
    val mono=treatment == BrandTreatment.Monochrome
    val blue=if(darkBackground)Color(0xFFAEC4FF) else Color(0xFF325CCB)
    Canvas(modifier.size(dimension).clearAndSetSemantics { if(label != null)contentDescription=label }) {
        scale(this.size.width/256f,this.size.height/256f,pivot=Offset.Zero) {
            repeat(5) { i -> rotate(72f*i,pivot=Offset(128f,128f)) { drawPath(petal,if(mono)monochromeColor else blue) } }
            drawCircle(if(mono)monochromeColor else Color(0xFFE9B85B),if(mono)9f else 12f,Offset(128f,128f))
        }
    }
}
