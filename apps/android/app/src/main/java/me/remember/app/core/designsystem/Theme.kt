package me.remember.app.core.designsystem

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
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
    val SageTint: Color @Composable get() = MaterialTheme.colorScheme.primaryContainer
    val ClayTint: Color @Composable get() = MaterialTheme.colorScheme.secondaryContainer
    val SkyTint: Color @Composable get() = MaterialTheme.colorScheme.surfaceVariant
    val LilacTint: Color @Composable get() = MaterialTheme.colorScheme.tertiaryContainer
    val GoldTint: Color @Composable get() = MaterialTheme.colorScheme.surfaceVariant
}
object RememberMeSpacing { val xs=4.dp; val sm=8.dp; val md=16.dp; val lg=24.dp; val xl=32.dp; val xxl=48.dp }
object RememberMeShapes { val small=8.dp; val medium=16.dp; val large=24.dp }
private val light = lightColorScheme(
    primary=Color(0xFF355C43), onPrimary=Color.White, primaryContainer=Color(0xFFE5EDDF), onPrimaryContainer=Color(0xFF233C31),
    secondary=Color(0xFF80501E), secondaryContainer=Color(0xFFF5E8CF), onSecondaryContainer=Color(0xFF80501E),
    tertiary=Color(0xFF355C43), background=Color(0xFFF4F5EC), onBackground=Color(0xFF233C31),
    surface=Color(0xFFFAFBF6), onSurface=Color(0xFF233C31), onSurfaceVariant=Color(0xFF496052),
    surfaceVariant=Color(0xFFFAFBF6), outline=Color(0xFF627865), outlineVariant=Color(0xFFD5DED0)
)
private val dark = darkColorScheme(
    primary=Color(0xFFB5D4BA), onPrimary=Color(0xFF183323), primaryContainer=Color(0xFF293F30), onPrimaryContainer=Color(0xFFEEF3E9),
    secondary=Color(0xFFF0C58B), secondaryContainer=Color(0xFF483924), onSecondaryContainer=Color(0xFFF0C58B),
    tertiary=Color(0xFFB5D4BA), background=Color(0xFF14251E), onBackground=Color(0xFFEEF3E9),
    surface=Color(0xFF21372B), onSurface=Color(0xFFEEF3E9), onSurfaceVariant=Color(0xFFB7CABB),
    surfaceVariant=Color(0xFF21372B), outline=Color(0xFF92B298), outlineVariant=Color(0xFF3C5445)
)
private fun text(size: Int, line: Int, weight: FontWeight = FontWeight.Normal) =
    TextStyle(fontFamily=FontFamily.SansSerif,fontSize=size.sp,lineHeight=line.sp,fontWeight=weight)
private val type = Typography(
    displayLarge=text(32,40,FontWeight.SemiBold), headlineLarge=text(26,36,FontWeight.SemiBold),
    headlineMedium=text(24,34,FontWeight.Medium), titleLarge=text(18,28,FontWeight.SemiBold),
    titleMedium=text(17,26,FontWeight.SemiBold), bodyLarge=text(17,26),bodyMedium=text(17,26),
    bodySmall=text(14,20),labelLarge=text(17,24,FontWeight.Medium),labelMedium=text(14,20,FontWeight.Medium),labelSmall=text(14,20)
)
@Composable fun RememberMeTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme=if(darkTheme) dark else light, typography=type,
        shapes=Shapes(small=RoundedCornerShape(8.dp),medium=RoundedCornerShape(14.dp),large=RoundedCornerShape(16.dp)),content={ CompositionLocalProvider(LocalContentColor provides MaterialTheme.colorScheme.onBackground) { content() } })
}
