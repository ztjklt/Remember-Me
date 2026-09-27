package me.remember.app.ui.components

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.draw.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.annotation.DrawableRes
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import me.remember.app.core.designsystem.*
import me.remember.app.R
import kotlin.math.sin
import androidx.compose.runtime.compositionLocalOf

val LocalHomeNavigation = compositionLocalOf<() -> Unit> { {} }

@Composable fun RmPage(content:@Composable ColumnScope.()->Unit){ val home = LocalHomeNavigation.current; Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)){ Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal=24.dp,vertical=28.dp),verticalArrangement=Arrangement.spacedBy(20.dp),content=content); IconButton(onClick=home,modifier=Modifier.align(Alignment.TopEnd).padding(8.dp)){ HugeIcon(R.drawable.hg_home,"Enter Portrait home",Modifier.size(24.dp),RememberMeColors.Moss) } } }
@Composable fun RmPrimaryButton(text:String,onClick:()->Unit,modifier:Modifier=Modifier){ Button(onClick,modifier.heightIn(min=52.dp),shape=MaterialTheme.shapes.medium){Text(text)} }
@Composable fun RmSecondaryButton(text:String,onClick:()->Unit){ RmSecondaryButton(text,Modifier,onClick) }
@Composable fun RmSecondaryButton(text:String,modifier:Modifier,onClick:()->Unit){ OutlinedButton(onClick,modifier.heightIn(min=52.dp),shape=MaterialTheme.shapes.medium){Text(text)} }
@Composable fun RmSectionHeader(title:String,meta:String?=null){ Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.Bottom){Text(title,style=MaterialTheme.typography.titleLarge); meta?.let{Text(it,style=MaterialTheme.typography.bodySmall,color=RememberMeColors.Muted)}} }
@Composable fun RmCaptureOrb(active:Boolean=false,onClick:()->Unit={}){
    val t=rememberInfiniteTransition(label="breath"); val scale by t.animateFloat(0.94f,1.04f,infiniteRepeatable(tween(1800,easing=FastOutSlowInEasing),RepeatMode.Reverse),label="scale")
    Box(Modifier.size(176.dp).scale(if(active) scale else 1f).clip(CircleShape).background(RememberMeColors.Clay.copy(alpha=.18f)).clickable(onClick=onClick).semantics{contentDescription=if(active)"正在聆听，点按停止" else "开始说"},contentAlignment=Alignment.Center){ Box(Modifier.size(116.dp).clip(CircleShape).background(RememberMeColors.Clay.copy(alpha=.42f)),contentAlignment=Alignment.Center){Text(if(active)"停止" else "开始说",fontWeight=FontWeight.Medium)} }
}
@Composable fun RmWaveform(active:Boolean=true){ Row(Modifier.fillMaxWidth().height(68.dp),horizontalArrangement=Arrangement.spacedBy(5.dp),verticalAlignment=Alignment.CenterVertically){ repeat(32){i->val h=if(active)(12+34*(.5+.5*sin(i*1.7))).dp else 8.dp; Box(Modifier.weight(1f).height(h).clip(CircleShape).background(RememberMeColors.Moss.copy(alpha=.65f))) } } }
@Composable fun RmVoicePlayer(title:String,subtitle:String="原始声音",playing:Boolean=false,onClick:()->Unit={}){ Row(Modifier.fillMaxWidth().clickable(onClick=onClick).padding(vertical=12.dp),verticalAlignment=Alignment.CenterVertically){ Box(Modifier.size(48.dp).clip(CircleShape).background(RememberMeColors.Moss),contentAlignment=Alignment.Center){Text(if(playing)"Ⅱ" else "▶",color=Color.White)}; Spacer(Modifier.width(16.dp)); Column{Text(title,fontWeight=FontWeight.Medium);Text(subtitle,color=RememberMeColors.Muted,style=MaterialTheme.typography.bodySmall)} } }
@Composable fun RmDivider()=HorizontalDivider(color=RememberMeColors.Line)

@Composable
fun HugeIcon(@DrawableRes icon: Int, contentDescription: String?, modifier: Modifier = Modifier, tint: Color = LocalContentColor.current) {
    Icon(
        painter = painterResource(icon),
        contentDescription = contentDescription,
        modifier = modifier,
        tint = tint
    )
}
