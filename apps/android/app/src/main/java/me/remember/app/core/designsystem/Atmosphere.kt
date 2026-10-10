package me.remember.app.core.designsystem

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.draw.paint
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import me.remember.app.R
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance

enum class NatureScene(val drawable: Int) {
    Meadow(R.drawable.rm_meadow_v7),
    Lake(R.drawable.rm_lake_v8),
    Forest(R.drawable.rm_forest_v8),
    Coast(R.drawable.rm_coast_v8),
    Night(R.drawable.rm_garden_night),
}

/** One static, bundled landscape per context. Reading surfaces use a stronger veil. */
@Composable
fun Modifier.atmosphere(immersive: Boolean = false, scene: NatureScene = NatureScene.Meadow): Modifier {
    val base = MaterialTheme.colorScheme.background
    val dark = base.luminance() < .5f
    return paint(painterResource(scene.drawable), sizeToIntrinsics = false,
        contentScale = ContentScale.Crop).drawWithCache {
        val veil = Brush.verticalGradient(listOf(
            base.copy(alpha = if (dark) .88f else if (immersive) .58f else .64f),
            base.copy(alpha = if (dark) .82f else if (immersive) .24f else .68f),
            base.copy(alpha = if (dark) .94f else if (immersive) .50f else .82f)))
        onDrawBehind { drawRect(veil) }
    }
}

@Composable
fun actionGradient(pressed: Boolean): Brush {
    val dark = MaterialTheme.colorScheme.background.luminance() < .5f
    val top = if(dark) Color(0xFFBED9C1) else Color(0xFF3F634C)
    val bottom = if(dark) Color(0xFFACCDB4) else Color(0xFF2D4F3C)
    return Brush.linearGradient(listOf(if(pressed) bottom else top,bottom))
}
