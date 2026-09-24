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

@Composable fun CreatorHomeScreen(memoryRepository: MemoryRepository, go: (String) -> Unit) {
    val memories by memoryRepository.memories().collectAsState(initial = Loadable.Loading)
    RmPage {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Remember Me", style = MaterialTheme.typography.headlineLarge)
            if (BuildConfig.DEBUG) Text("•••", Modifier.clickable { go(Routes.Debug) }.padding(12.dp))
        }
        Text("今天想留下些什么？", style = MaterialTheme.typography.headlineMedium)
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { RmCaptureOrb { go(Routes.Recording) } }
        RmDivider()
        RmSectionHeader("最近的记忆", "查看全部")
        when (val state = memories) {
            is Loadable.Content -> Text(
                state.value.firstOrNull()?.story.orEmpty(),
                Modifier.clickable { go(Routes.Memories) }.padding(vertical = 8.dp),
                style = MaterialTheme.typography.bodyLarge
            )
            Loadable.Empty -> Text("还没有真实记忆。上传录音并完成处理后会出现在这里。", color = RememberMeColors.Muted)
            Loadable.Loading -> CircularProgressIndicator()
            is Loadable.Error -> Text(state.message, color = MaterialTheme.colorScheme.error)
        }
        NavigationRow(go)
    }
}
@Composable private fun NavigationRow(go:(String)->Unit){Row(Modifier.fillMaxWidth().padding(top=12.dp),horizontalArrangement=Arrangement.SpaceAround){listOf("Home" to Routes.Home,"Memories" to Routes.Memories,"Capture" to Routes.Recording,"Twin" to Routes.Twin).forEach{(label,r)->Text(label,Modifier.clickable{go(r)}.padding(10.dp),style=MaterialTheme.typography.labelMedium)}}}

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

@Composable fun TwinScreen(back:()->Unit){var asked by remember{mutableStateOf(false)};RmPage{TextButton(back){Text("← 返回")};Text("我还在慢慢认识你。",style=MaterialTheme.typography.headlineLarge);Text("回答会区分你的原话与 AI Simulation。",color=RememberMeColors.Muted);OutlinedTextField("我小时候最喜欢什么？",{},Modifier.fillMaxWidth(),readOnly=true,label={Text("问一个问题")});RmPrimaryButton("问问 Twin",{asked=true},Modifier.fillMaxWidth());if(asked){RmSectionHeader("你曾经说过","ORIGINAL");RmVoicePlayer("外婆家窗边那只旧收音机","2012 · 襄阳 · 原始录音");RmDivider();RmSectionHeader("Based on what you’ve told me…","AI SIMULATION");Text("你珍惜的也许不是那台收音机本身，而是它让一家人安静地待在一起。",style=MaterialTheme.typography.bodyLarge)}}}

@Composable fun CalibrationScreen(back:()->Unit){var step by remember{mutableIntStateOf(0)};RmPage{TextButton(back){Text("← 返回")};Text("看看我是不是真的了解你。",style=MaterialTheme.typography.headlineLarge);Text("如果你有一份稳定但没有兴趣的工作，和一个风险很高但非常想做的项目，你会怎么选？",style=MaterialTheme.typography.titleLarge);Text("Twin Answer · LOCKED",color=RememberMeColors.Muted);Text("我会给想做的项目设一个六个月期限。如果基本生活不受影响，我愿意承担风险。",style=MaterialTheme.typography.bodyLarge);if(step==0)RmPrimaryButton("写下你的答案",{step=1},Modifier.fillMaxWidth()) else {OutlinedTextField("我可能会先存够半年的钱，再试一次。",{},Modifier.fillMaxWidth());RmSectionHeader("Compare");listOf("Decision  接近","Reasoning  有差异","Values  接近","Emotion  尚不确定","Expression  有差异").forEach{Text(it)} }}}

@Composable fun HandoverScreen(back:()->Unit)=RmPage{TextButton(back){Text("← 返回")};Text("数字托付",style=MaterialTheme.typography.headlineLarge);Text("如果未来你无法继续使用 Remember Me，你希望谁可以收到什么？",style=MaterialTheme.typography.titleLarge);listOf("妈妈" to "Memories · Original Voice","伴侣" to "Memories · Messages · Twin Chat","孩子" to "For You messages","朋友" to "Selected memories").forEach{(p,s)->Column(Modifier.padding(vertical=10.dp)){Text(p,fontWeight=FontWeight.Medium);Text(s,color=RememberMeColors.Muted);RmDivider()}};Text("每个人的访问范围都可以不同，也可以随时撤回。",color=RememberMeColors.Muted)}
