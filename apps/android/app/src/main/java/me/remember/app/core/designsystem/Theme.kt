package me.remember.app.core.designsystem

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

object RememberMeColors {
    val Paper: Color @Composable get() = MaterialTheme.colorScheme.background
    val Surface: Color @Composable get() = MaterialTheme.colorScheme.surface
    val Ink: Color @Composable get() = MaterialTheme.colorScheme.onSurface
    val Muted: Color @Composable get() = MaterialTheme.colorScheme.onSurfaceVariant
    val Moss: Color @Composable get() = MaterialTheme.colorScheme.primary
    val Clay: Color @Composable get() = MaterialTheme.colorScheme.tertiary
    val Line: Color @Composable get() = MaterialTheme.colorScheme.outlineVariant
}
object RememberMeSpacing { val xs=4.dp; val sm=8.dp; val md=16.dp; val lg=24.dp; val xl=32.dp; val xxl=48.dp }
object RememberMeShapes { val small=8.dp; val medium=16.dp; val large=24.dp }
private val light = lightColorScheme(
    primary=Color(0xFF325CCB), onPrimary=Color.White, primaryContainer=Color(0xFFEEF2FC), onPrimaryContainer=Color(0xFF20242C),
    secondary=Color(0xFF325CCB), secondaryContainer=Color(0xFFEEF2FC), onSecondaryContainer=Color(0xFF20242C),
    tertiary=Color(0xFF325CCB), background=Color(0xFFFFFFFF), onBackground=Color(0xFF20242C),
    surface=Color(0xFFF5F6F8), onSurface=Color(0xFF20242C), onSurfaceVariant=Color(0xFF626975),
    surfaceVariant=Color(0xFFF5F6F8), outline=Color(0xFF677994), outlineVariant=Color(0xFFE5E7EB)
)
private val dark = darkColorScheme(
    primary=Color(0xFFA9C0FF), onPrimary=Color(0xFF152B59), primaryContainer=Color(0xFF252C3D), onPrimaryContainer=Color(0xFFF0F1F4),
    secondary=Color(0xFFA9C0FF), secondaryContainer=Color(0xFF252C3D), onSecondaryContainer=Color(0xFFF0F1F4),
    tertiary=Color(0xFFA9C0FF), background=Color(0xFF15171C), onBackground=Color(0xFFF0F1F4),
    surface=Color(0xFF202329), onSurface=Color(0xFFF0F1F4), onSurfaceVariant=Color(0xFFADB3BF),
    surfaceVariant=Color(0xFF202329), outline=Color(0xFF98ABC8), outlineVariant=Color(0xFF343942)
)
private fun text(size: Int, line: Int, weight: FontWeight = FontWeight.Normal) =
    TextStyle(fontFamily=FontFamily.SansSerif,fontSize=size.sp,lineHeight=line.sp,fontWeight=weight)
private val type = Typography(
    displayLarge=text(32,40,FontWeight.SemiBold), headlineLarge=text(26,36,FontWeight.Medium),
    headlineMedium=text(24,34,FontWeight.Medium), titleLarge=text(18,28,FontWeight.Medium),
    titleMedium=text(17,26,FontWeight.Medium), bodyLarge=text(17,26),bodyMedium=text(17,26),
    bodySmall=text(14,20),labelLarge=text(17,24,FontWeight.Medium),labelMedium=text(14,20,FontWeight.Medium),labelSmall=text(14,20)
)
@Composable fun RememberMeTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme=if(darkTheme) dark else light, typography=type,
        shapes=Shapes(small=RoundedCornerShape(8.dp),medium=RoundedCornerShape(14.dp),large=RoundedCornerShape(16.dp)),content=content)
}
