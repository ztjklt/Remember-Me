package me.remember.app.feature

import androidx.compose.animation.*
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import me.remember.app.core.designsystem.RememberMeColors
import me.remember.app.ui.components.*

@Composable fun SplashScreen(next:()->Unit){ LaunchedEffect(Unit){delay(850);next()}; Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center){Text("Remember Me",style=MaterialTheme.typography.headlineLarge)} }
@Composable fun WelcomeScreen(next:()->Unit)=RmPage{Spacer(Modifier.weight(1f));Text("Remember Me",style=MaterialTheme.typography.bodyLarge,color=RememberMeColors.Muted);Text("留下一个，\n可以被理解的你。",style=MaterialTheme.typography.displayLarge);Text("通过你的声音，我会慢慢认识你的故事、重要的人，和你看待世界的方式。",style=MaterialTheme.typography.bodyLarge,color=RememberMeColors.Muted);Spacer(Modifier.weight(1f));RmPrimaryButton("开始",next,Modifier.fillMaxWidth())}
@Composable fun ExplanationScreen(next:()->Unit)=RmPage{Spacer(Modifier.height(44.dp));Text("这不是一次测试。",style=MaterialTheme.typography.headlineLarge);Text("只是从你的声音开始。",color=RememberMeColors.Muted);Spacer(Modifier.height(20.dp));listOf("自然地说。" to "Speak naturally.","我会慢慢记住。" to "We remember.","你始终拥有控制权。" to "You stay in control.").forEach{(a,b)->Column(Modifier.padding(vertical=10.dp)){Text(a,style=MaterialTheme.typography.titleLarge);Text(b,color=RememberMeColors.Muted)}};Spacer(Modifier.weight(1f));RmPrimaryButton("继续",next,Modifier.fillMaxWidth())}
@Composable fun ConsentScreen(next:()->Unit){var recording by remember{mutableStateOf(true)};var cloud by remember{mutableStateOf(true)};var voice by remember{mutableStateOf(true)};RmPage{Text("由你决定留下什么。",style=MaterialTheme.typography.headlineLarge);Text("每一种使用方式都需要单独同意。以后可以随时撤回。",color=RememberMeColors.Muted);Permission("录音授权","用于保存你的原始声音与故事",recording){recording=it};Permission("云端 Twin 授权","用于跨设备保存结构化记忆与理解",cloud){cloud=it};Permission("声音克隆授权","用于生成明确标记的声音模拟；不等同于录音授权",voice){voice=it};Spacer(Modifier.weight(1f));RmPrimaryButton("同意并继续",next,Modifier.fillMaxWidth())}}
@Composable private fun Permission(title:String,body:String,checked:Boolean,onChange:(Boolean)->Unit){Row(Modifier.fillMaxWidth().padding(vertical=10.dp),verticalAlignment=Alignment.Top){Column(Modifier.weight(1f)){Text(title,style=MaterialTheme.typography.titleLarge);Text(body,color=RememberMeColors.Muted)};Switch(checked,onChange)}}
@Composable fun IntroduceScreen(next:()->Unit)=RmPage{Text("先介绍一下你自己吧。",style=MaterialTheme.typography.headlineLarge);Text("不用准备。\n想到什么，就说什么。",color=RememberMeColors.Muted);Spacer(Modifier.height(24.dp));Box(Modifier.fillMaxWidth(),contentAlignment=Alignment.Center){RmCaptureOrb(onClick=next)};Spacer(Modifier.weight(1f));Text("第一次介绍只属于你。你可以随时暂停或删除。",style=MaterialTheme.typography.bodySmall,color=RememberMeColors.Muted,textAlign=TextAlign.Center,modifier=Modifier.fillMaxWidth())}
