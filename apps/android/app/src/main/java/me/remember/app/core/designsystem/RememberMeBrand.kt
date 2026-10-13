package me.remember.app.core.designsystem

import androidx.compose.foundation.Image
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.graphics.luminance
import me.remember.app.R

enum class BrandTreatment { Auto, Material, Flat, Monochrome }

/** Botanical brand v2. Static identity only, never a recording/progress indicator. */
@Composable
fun RememberMeBrand(
    modifier: Modifier = Modifier,
    size: Dp = 48.dp,
    treatment: BrandTreatment = BrandTreatment.Auto,
    darkBackground: Boolean = MaterialTheme.colorScheme.background.luminance() < .5f,
    materialPainter: Painter? = null,
    monochromeColor: Color = if(darkBackground) Color(0xFFEEF3E9) else Color(0xFF355C43),
    label: String? = null,
) {
    val dimension = size.coerceAtLeast(16.dp)
    val useMaterial = materialPainter != null &&
        (treatment == BrandTreatment.Material || (treatment == BrandTreatment.Auto && dimension >= 64.dp))
    val mono = treatment == BrandTreatment.Monochrome
    val asset = when {
        mono -> R.drawable.rm_brand_botanical_mono
        darkBackground -> R.drawable.rm_brand_botanical_dark
        else -> R.drawable.rm_brand_botanical_light
    }
    Image(painter = if (useMaterial) materialPainter!! else painterResource(asset),
        contentDescription = label, modifier = modifier.size(dimension),
        colorFilter = if (mono && !useMaterial) ColorFilter.tint(monochromeColor) else null)
}
