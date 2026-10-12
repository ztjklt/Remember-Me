package me.remember.app.core.designsystem

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
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
    surfaceVariant=Color(0xFFFAFBF6), outline=Color(0xFF627865), outlineVariant=Color(0xFFD5DED0), surfaceTint=Color(0xFF355C43),
    surfaceDim=Color(0xFFDEE3D7),surfaceBright=Color(0xFFFAFBF6),surfaceContainerLowest=Color(0xFFFFFFFF),
    surfaceContainerLow=Color(0xFFF4F6ED),surfaceContainer=Color(0xFFEDF0E5),
    surfaceContainerHigh=Color(0xFFE6EBDD),surfaceContainerHighest=Color(0xFFDDE5D6)
)
private val dark = darkColorScheme(
    primary=Color(0xFFB5D4BA), onPrimary=Color(0xFF183323), primaryContainer=Color(0xFF293F30), onPrimaryContainer=Color(0xFFEEF3E9),
    secondary=Color(0xFFF0C58B), secondaryContainer=Color(0xFF483924), onSecondaryContainer=Color(0xFFF0C58B),
    tertiary=Color(0xFFB5D4BA), background=Color(0xFF14251E), onBackground=Color(0xFFEEF3E9),
    surface=Color(0xFF21372B), onSurface=Color(0xFFEEF3E9), onSurfaceVariant=Color(0xFFB7CABB),
    surfaceVariant=Color(0xFF21372B), outline=Color(0xFF92B298), outlineVariant=Color(0xFF3C5445),surfaceTint=Color(0xFFB5D4BA),
    surfaceDim=Color(0xFF14251E),surfaceBright=Color(0xFF334B3E),surfaceContainerLowest=Color(0xFF102017),
    surfaceContainerLow=Color(0xFF1B3025),surfaceContainer=Color(0xFF21372B),
    surfaceContainerHigh=Color(0xFF294132),surfaceContainerHighest=Color(0xFF334B3E)
)
private fun text(size: Int, line: Int, weight: FontWeight = FontWeight.Normal) =
    TextStyle(fontFamily=FontFamily.SansSerif,fontSize=size.sp,lineHeight=line.sp,fontWeight=weight)
private val type = Typography(
    displayLarge=text(32,40,FontWeight.SemiBold),displayMedium=text(38,46,FontWeight.Medium),
    displaySmall=text(32,40,FontWeight.Medium),headlineSmall=text(22,32,FontWeight.Medium),titleSmall=text(15,22,FontWeight.SemiBold),
    headlineLarge=text(26,36,FontWeight.SemiBold),
    headlineMedium=text(24,34,FontWeight.Medium), titleLarge=text(18,28,FontWeight.SemiBold),
    titleMedium=text(17,26,FontWeight.SemiBold), bodyLarge=text(17,26),bodyMedium=text(17,26),
    bodySmall=text(14,20),labelLarge=text(17,24,FontWeight.Medium),labelMedium=text(14,20,FontWeight.Medium),labelSmall=text(14,20)
)
val LocalSimpleMode = staticCompositionLocalOf { false }
private val simpleType = type.copy(
    headlineLarge=text(26,36,FontWeight.SemiBold), headlineMedium=text(24,34,FontWeight.SemiBold),
    headlineSmall=text(24,34,FontWeight.SemiBold), titleLarge=text(22,32,FontWeight.SemiBold),
    titleMedium=text(20,30,FontWeight.SemiBold), bodyLarge=text(20,30), bodyMedium=text(20,30),
    bodySmall=text(17,26), labelLarge=text(20,28,FontWeight.Medium), labelMedium=text(17,26,FontWeight.Medium), labelSmall=text(17,26)
)
@Composable fun RememberMeTheme(darkTheme: Boolean = isSystemInDarkTheme(), simpleMode: Boolean = false, content: @Composable () -> Unit) {
    MaterialTheme(colorScheme=if(darkTheme) dark else light, typography=if(simpleMode) simpleType else type,
        shapes=Shapes(small=RoundedCornerShape(8.dp),medium=RoundedCornerShape(14.dp),large=RoundedCornerShape(16.dp)),content={ CompositionLocalProvider(LocalSimpleMode provides simpleMode, LocalContentColor provides MaterialTheme.colorScheme.onBackground) { content() } })
}
