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
    primary=Color(0xFF325CCB), onPrimary=Color.White, primaryContainer=Color(0xFFDDE6FA), onPrimaryContainer=Color(0xFF17243B),
    secondary=Color(0xFF325CCB), secondaryContainer=Color(0xFFDDE6FA), onSecondaryContainer=Color(0xFF17243B),
    tertiary=Color(0xFF325CCB), background=Color(0xFFEEF1F6), onBackground=Color(0xFF17243B),
    surface=Color(0xFFFCFDFF), onSurface=Color(0xFF17243B), onSurfaceVariant=Color(0xFF56647B),
    surfaceVariant=Color(0xFFE4EAF4), outline=Color(0xFF677994), outlineVariant=Color(0xFFCCD5E5)
)
private val dark = darkColorScheme(
    primary=Color(0xFFA9C0FF), onPrimary=Color(0xFF152B59), primaryContainer=Color(0xFF243755), onPrimaryContainer=Color(0xFFEDF2FF),
    secondary=Color(0xFFA9C0FF), secondaryContainer=Color(0xFF243755), onSecondaryContainer=Color(0xFFEDF2FF),
    tertiary=Color(0xFFA9C0FF), background=Color(0xFF101722), onBackground=Color(0xFFEDF2FF),
    surface=Color(0xFF192333), onSurface=Color(0xFFEDF2FF), onSurfaceVariant=Color(0xFFABBAD3),
    surfaceVariant=Color(0xFF243044), outline=Color(0xFF98ABC8), outlineVariant=Color(0xFF354764)
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
