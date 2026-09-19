package me.remember.app.core.designsystem

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

object RememberMeColors {
    val Paper = Color(0xFFF7F3EC); val Surface = Color(0xFFFFFCF7)
    val Ink = Color(0xFF292A27); val Muted = Color(0xFF77736B)
    val Moss = Color(0xFF68766A); val Clay = Color(0xFFB98268); val Line = Color(0xFFE1DBD1)
}
object RememberMeSpacing { val xs=4.dp; val sm=8.dp; val md=16.dp; val lg=24.dp; val xl=36.dp; val xxl=56.dp }
object RememberMeShapes { val small=8.dp; val medium=16.dp; val large=28.dp }

private val scheme = lightColorScheme(
    primary=RememberMeColors.Moss, onPrimary=Color.White, secondary=RememberMeColors.Clay,
    background=RememberMeColors.Paper, onBackground=RememberMeColors.Ink,
    surface=RememberMeColors.Surface, onSurface=RememberMeColors.Ink,
    outline=RememberMeColors.Line
)
private val type = Typography(
    displayLarge=Typography().displayLarge.copy(fontFamily=FontFamily.Serif,fontSize=46.sp,lineHeight=54.sp,fontWeight=FontWeight.Normal),
    headlineLarge=Typography().headlineLarge.copy(fontFamily=FontFamily.Serif,fontSize=34.sp,lineHeight=42.sp),
    headlineMedium=Typography().headlineMedium.copy(fontFamily=FontFamily.Serif,fontSize=27.sp,lineHeight=35.sp),
    titleLarge=Typography().titleLarge.copy(fontSize=20.sp,fontWeight=FontWeight.Medium),
    bodyLarge=Typography().bodyLarge.copy(fontSize=17.sp,lineHeight=27.sp),
    bodyMedium=Typography().bodyMedium.copy(fontSize=15.sp,lineHeight=23.sp),
    labelLarge=Typography().labelLarge.copy(fontSize=15.sp,fontWeight=FontWeight.Medium)
)
@Composable fun RememberMeTheme(content:@Composable()->Unit)=MaterialTheme(colorScheme=scheme,typography=type,content=content)
