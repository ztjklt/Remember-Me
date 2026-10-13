package me.remember.app.core.designsystem

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
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
    Path(R.drawable.rm_garden_path),
}

/** One static, bundled landscape per context. Reading surfaces use a stronger veil. */
@Composable
fun Modifier.atmosphere(immersive: Boolean = false, scene: NatureScene = NatureScene.Meadow): Modifier {
    // The bundled landscape is the actual page background. Do not place a
    // full-screen dark veil between the UI and the image.
    return paint(painterResource(scene.drawable), sizeToIntrinsics = false,
        contentScale = ContentScale.Crop)
}

@Composable
fun actionGradient(pressed: Boolean): Brush {
    val dark = MaterialTheme.colorScheme.background.luminance() < .5f
    val top = if(dark) Color(0xFFBED9C1) else Color(0xFF3F634C)
    val bottom = if(dark) Color(0xFFACCDB4) else Color(0xFF2D4F3C)
    return Brush.linearGradient(listOf(if(pressed) bottom else top,bottom))
}
