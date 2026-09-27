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
    primary=Color(0xFF54685B), onPrimary=Color.White, primaryContainer=Color(0xFFE4EBE1), onPrimaryContainer=Color(0xFF263D2D),
    secondary=Color(0xFF54685B), secondaryContainer=Color(0xFFE4EBE1), onSecondaryContainer=Color(0xFF263D2D),
    tertiary=Color(0xFF975139), background=Color(0xFFF8F5EF), onBackground=Color(0xFF262923),
    surface=Color(0xFFFFFDFA), onSurface=Color(0xFF262923), onSurfaceVariant=Color(0xFF61665F),
    surfaceVariant=Color(0xFFEEEDE5), outline=Color(0xFF777D72), outlineVariant=Color(0xFFDCDDD3)
)
private val dark = darkColorScheme(
    primary=Color(0xFFACC7AF), onPrimary=Color(0xFF203527), primaryContainer=Color(0xFF344D3B), onPrimaryContainer=Color(0xFFCEE5CB),
    secondary=Color(0xFFACC7AF), secondaryContainer=Color(0xFF344D3B), onSecondaryContainer=Color(0xFFCEE5CB),
    tertiary=Color(0xFFE8AC92), background=Color(0xFF1A1D1B), onBackground=Color(0xFFF1F2EC),
    surface=Color(0xFF242925), onSurface=Color(0xFFF1F2EC), onSurfaceVariant=Color(0xFFB8C0B6),
    surfaceVariant=Color(0xFF303830), outline=Color(0xFF939E91), outlineVariant=Color(0xFF465046)
)
private fun text(size: Int, line: Int, weight: FontWeight = FontWeight.Normal) =
    TextStyle(fontFamily=FontFamily.SansSerif,fontSize=size.sp,lineHeight=line.sp,fontWeight=weight)
private val type = Typography(
    displayLarge=text(32,40,FontWeight.SemiBold), headlineLarge=text(28,36,FontWeight.SemiBold),
    headlineMedium=text(24,32,FontWeight.SemiBold), titleLarge=text(20,28,FontWeight.SemiBold),
    titleMedium=text(17,26,FontWeight.Medium), bodyLarge=text(17,26),bodyMedium=text(17,26),
    bodySmall=text(14,20),labelLarge=text(17,24,FontWeight.Medium),labelMedium=text(14,20,FontWeight.Medium),labelSmall=text(14,20)
)
@Composable fun RememberMeTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme=if(darkTheme) dark else light, typography=type,
        shapes=Shapes(small=RoundedCornerShape(8.dp),medium=RoundedCornerShape(16.dp),large=RoundedCornerShape(24.dp)),content=content)
}
