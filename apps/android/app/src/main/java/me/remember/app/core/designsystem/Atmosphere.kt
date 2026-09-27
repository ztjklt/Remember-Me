package me.remember.app.core.designsystem

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance

/** Static color fields with a lower content veil; no blur, timers or decorative motion. */
@Composable
fun Modifier.atmosphere(): Modifier {
    val base = MaterialTheme.colorScheme.background
    val dark = base.luminance() < .5f
    val blue = if (dark) Color(0xFF22324B) else Color(0xFFD7E3F3)
    val violet = if (dark) Color(0xFF302B43) else Color(0xFFE6DFF0)
    val sand = if (dark) Color(0xFF202C34) else Color(0xFFEEE5DE)
    return drawWithCache {
        val field = Brush.linearGradient(listOf(blue, sand), end=Offset(size.width, size.height))
        val glow = Brush.radialGradient(listOf(violet, violet.copy(alpha=0f)),
            center=Offset(size.width, size.height*.28f),radius=size.maxDimension*.7f)
        val veil = Brush.verticalGradient(listOf(base.copy(alpha=0f),base.copy(alpha=.3f),base))
        onDrawBehind { drawRect(field); drawRect(glow); drawRect(veil) }
    }
}

@Composable
fun actionGradient(pressed: Boolean): Brush {
    val dark = MaterialTheme.colorScheme.background.luminance() < .5f
    val top = if(dark) Color(0xFFB8CCF4) else Color(0xFF4266BC)
    val bottom = if(dark) Color(0xFFA3B7E8) else Color(0xFF344DAA)
    return Brush.linearGradient(listOf(if(pressed) bottom else top,bottom))
}
