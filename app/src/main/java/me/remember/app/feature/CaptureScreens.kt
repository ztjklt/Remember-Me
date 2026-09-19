package me.remember.app.feature

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import me.remember.app.core.designsystem.RememberMeColors
import me.remember.app.ui.components.*

@Composable fun RecordingScreen(done:()->Unit){var seconds by remember{mutableIntStateOf(0)};LaunchedEffect(Unit){while(true){delay(1000);seconds++}};RmPage{Text("我在听。",style=MaterialTheme.typography.headlineLarge);Text("%02d:%02d".format(seconds/60,seconds%60),color=RememberMeColors.Muted);RmWaveform();Box(Modifier.fillMaxWidth(),contentAlignment=Alignment.Center){RmCaptureOrb(true,done)};Text("你可以说",style=MaterialTheme.typography.titleLarge);listOf("我是谁","我现在的生活","对我重要的人","我最近在想什么").forEach{Text("“$it”",color=RememberMeColors.Muted)};Spacer(Modifier.weight(1f))}}
@Composable fun ProcessingScreen(done:()->Unit){var n by remember{mutableIntStateOf(0)};LaunchedEffect(Unit){repeat(3){delay(650);n++};delay(600);done()};RmPage{Spacer(Modifier.height(80.dp));Text("我正在认识你。",style=MaterialTheme.typography.headlineLarge);Text("不是为了给你下定义，只是把你说过的话慢慢放在一起。",color=RememberMeColors.Muted);Spacer(Modifier.height(30.dp));listOf("我听到了你的名字。","我知道了一些对你重要的人。","我开始记住你的声音。").forEachIndexed{i,t->if(n>i){Text("✓  $t",style=MaterialTheme.typography.bodyLarge)}};Spacer(Modifier.weight(1f));Text("Identity Seed  ·  Memory Seed  ·  Voice Seed",style=MaterialTheme.typography.bodySmall,color=RememberMeColors.Muted)}}
@Composable fun TwinBirthScreen(next:()->Unit)=RmPage{Spacer(Modifier.height(24.dp));Text("我开始认识你了。",style=MaterialTheme.typography.headlineLarge);Text("陈屿",style=MaterialTheme.typography.displayLarge);Text("独立纪录片剪辑师  ·  杭州",color=RememberMeColors.Muted);RmDivider();Text("你很重视",style=MaterialTheme.typography.titleLarge);Text("创造   家人   诚实地生活",style=MaterialTheme.typography.headlineMedium);RmDivider();Text("我目前知道",style=MaterialTheme.typography.titleLarge);Text("3 个重要的人\n4 段经历\n2 个长期兴趣",style=MaterialTheme.typography.bodyLarge);Spacer(Modifier.weight(1f));Text("我才刚刚开始认识你。",color=RememberMeColors.Muted);RmPrimaryButton("继续",next,Modifier.fillMaxWidth())}
@Composable fun VoiceSeedScreen(next:()->Unit){var playing by remember{mutableStateOf(false)};RmPage{Text("我也开始记住你的声音了。",style=MaterialTheme.typography.headlineLarge);Text("VOICE SEED",color=RememberMeColors.Muted);Text("Ready for preview",style=MaterialTheme.typography.titleLarge);RmVoicePlayer("听听现在的我","声音模拟 · Preview",playing){playing=!playing};if(playing)RmWaveform();Spacer(Modifier.weight(1f));RmSecondaryButton("重新录一点"){};TextButton(onClick={}){Text("这个声音还不像我")};RmPrimaryButton("进入 Remember Me",next,Modifier.fillMaxWidth())}}
