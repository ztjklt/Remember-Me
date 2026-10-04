package me.remember.app.feature

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import me.remember.app.core.designsystem.RememberMeColors
import me.remember.app.BuildConfig
import me.remember.app.data.repository.MemoryRepository
import me.remember.app.model.*
import me.remember.app.navigation.Routes
import me.remember.app.ui.components.*

/**
 * Direction A, the minimal capture home.
 *
 * One action, in plain Chinese, sized for a Subject who may be elderly or unwell: press the
 * orb and speak. Everything else on this screen exists to answer "does it remember?", and
 * the deep view is deliberately a single quiet entry rather than a mode switch — the person
 * this is built for should never have to pick a mode.
 */
@Composable fun CreatorHomeScreen(memoryRepository: MemoryRepository, go: (String) -> Unit) {
    val memories by memoryRepository.memories().collectAsState(initial = Loadable.Loading)
    RmPage {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            if (BuildConfig.DEBUG) Text("•••", Modifier.clickable { go(Routes.Debug) }.padding(12.dp))
        }
        Text("今天想留下些什么？", style = MaterialTheme.typography.headlineMedium)
        Text("想说什么就说什么，说完我来整理。", color = RememberMeColors.Muted, style = MaterialTheme.typography.bodyLarge)
        Box(Modifier.fillMaxWidth().padding(vertical = 16.dp), contentAlignment = Alignment.Center) {
            RmCaptureOrb { go(Routes.Recording) }
        }
        RmDivider()
        val known = (memories as? Loadable.Content)?.value.orEmpty()
        RmSectionHeader("它还记得", if (known.isEmpty()) null else "${known.size} 条")
        when (val state = memories) {
            is Loadable.Content -> Text(
                "“${state.value.firstOrNull()?.story.orEmpty()}”",
                Modifier.clickable { go(Routes.Memories) }.padding(vertical = 8.dp),
                style = MaterialTheme.typography.bodyLarge
            )
            Loadable.Empty -> Text("还什么都没有。按上面那个圆，说一段试试。", color = RememberMeColors.Muted)
            Loadable.Loading -> CircularProgressIndicator()
            is Loadable.Error -> Text(state.message, color = MaterialTheme.colorScheme.error)
        }
        NavigationRow(go)
    }
}
@Composable private fun NavigationRow(go:(String)->Unit){Row(Modifier.fillMaxWidth().padding(top=12.dp),horizontalArrangement=Arrangement.SpaceAround){listOf("我说过的" to Routes.Memories,"AI 的理解" to Routes.Understanding,"Twin" to Routes.Twin).forEach{(label,r)->Text(label,Modifier.clickable{go(r)}.padding(10.dp),style=MaterialTheme.typography.bodyLarge)}}}

@Composable fun MemoriesScreen(memoryRepository:MemoryRepository,back:()->Unit){val state by memoryRepository.memories().collectAsState(initial=Loadable.Loading);RmPage{TextButton(back){Text("← 返回")};Text("Memory Archive",style=MaterialTheme.typography.headlineLarge);Text("这里只展示 Backend 返回的提取结果。",color=RememberMeColors.Muted);when(val s=state){is Loadable.Content->s.value.forEach{m->MemoryItem(m)};Loadable.Loading->CircularProgressIndicator();Loadable.Empty->Text("还没有真实记忆");is Loadable.Error->Text(s.message)}}}
@Composable private fun MemoryItem(m:Memory){Column(Modifier.padding(vertical=12.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
    val location=listOf(m.date,m.place).filter{it.isNotBlank()}.joinToString(" · ")
    if(location.isNotBlank())Text(location,color=RememberMeColors.Muted)
    Text("“${m.story}”",style=MaterialTheme.typography.titleLarge)
    val labels=m.people+m.tags
    if(labels.isNotEmpty())Text(labels.joinToString("   "),style=MaterialTheme.typography.bodySmall,color=RememberMeColors.Muted)
    m.episodeId?.let{Text("Episode：$it",style=MaterialTheme.typography.bodySmall,color=RememberMeColors.Muted)}
    if(m.sourceType!=null)Text("${m.memoryType} · ${m.sourceType} · confidence ${m.confidence}",style=MaterialTheme.typography.bodySmall,color=RememberMeColors.Muted)
    if(m.evidenceIds.isNotEmpty())Text("证据：${m.evidenceIds.joinToString()}",style=MaterialTheme.typography.bodySmall,color=RememberMeColors.Muted)
    m.modelVersion?.let{Text("模型：$it",style=MaterialTheme.typography.bodySmall,color=RememberMeColors.Muted)}
    if(m.hasPlayableAudio)RmVoicePlayer(m.duration)
    RmDivider()
}}



@Composable fun HandoverScreen(back:()->Unit)=RmPage{TextButton(back){Text("← 返回")};Text("数字托付",style=MaterialTheme.typography.headlineLarge);Text("如果未来你无法继续使用 Remember Me，你希望谁可以收到什么？",style=MaterialTheme.typography.titleLarge);listOf("妈妈" to "Memories · Original Voice","伴侣" to "Memories · Messages · Twin Chat","孩子" to "For You messages","朋友" to "Selected memories").forEach{(p,s)->Column(Modifier.padding(vertical=10.dp)){Text(p,fontWeight=FontWeight.Medium);Text(s,color=RememberMeColors.Muted);RmDivider()}};Text("每个人的访问范围都可以不同，也可以随时撤回。",color=RememberMeColors.Muted)}
