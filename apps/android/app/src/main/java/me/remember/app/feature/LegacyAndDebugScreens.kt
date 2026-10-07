package me.remember.app.feature

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import me.remember.app.core.designsystem.RememberMeColors
import me.remember.app.navigation.Routes
import me.remember.app.ui.components.*

@Composable fun LegacyHomeScreen(ask:()->Unit)=RmPage{Text("演示页面 · 以下为虚构数据");Text("REMEMBER",color=RememberMeColors.Muted);Text("妈妈",style=MaterialTheme.typography.displayLarge);Text("1968 — 2047",color=RememberMeColors.Muted);Text("她为你留下了\n127 段声音   43 个故事\n6 条只留给你的内容",style=MaterialTheme.typography.bodyLarge);RmDivider();RmSectionHeader("Her Voice");RmVoicePlayer("今天别忘了吃早饭","原始声音 · 00:31");RmDivider();RmSectionHeader("Her Life");Text("Childhood  ·  School  ·  Family\nCareer  ·  Later Years",style=MaterialTheme.typography.titleLarge);RmDivider();RmSectionHeader("Important People");Text("外婆   爸爸   林夏   周老师",color=RememberMeColors.Muted);RmDivider();RmSectionHeader("For You");Text("只在你需要的时候打开。",style=MaterialTheme.typography.titleLarge);Spacer(Modifier.weight(1f));RmSecondaryButton("Ask Her",ask)}

@Composable fun DemoMenuScreen(go:(String)->Unit,back:()->Unit)=RmPage{TextButton(back){Text("← 返回")};Text("Demo Menu",style=MaterialTheme.typography.headlineLarge);Text("Debug build only · 产品评审快捷入口",color=RememberMeColors.Muted);listOf("Reset onboarding" to Routes.Welcome,"Skip onboarding" to Routes.Home,"Open Creator Home" to Routes.Home,"Open Twin Birth" to Routes.Birth,"Open Voice Seed" to Routes.Voice,"Open Calibration" to Routes.Calibration,"Open Handover" to Routes.Handover,"Switch to Legacy Mode" to Routes.Legacy,"Simulate loading" to Routes.Processing,"Simulate error" to Routes.Memories).forEach{(label,route)->Row(Modifier.fillMaxWidth().clickable{go(route)}.padding(vertical=14.dp)){Text(label)};RmDivider()}}
