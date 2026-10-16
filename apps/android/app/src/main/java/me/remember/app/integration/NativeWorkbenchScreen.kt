package me.remember.app.integration

import android.Manifest
import android.os.Build
import android.app.Activity
import android.content.ContextWrapper
import androidx.core.view.WindowCompat
import androidx.compose.ui.platform.LocalView
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.selection.toggleable
import androidx.compose.ui.semantics.Role
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.toArgb
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import kotlinx.coroutines.launch
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import me.remember.app.core.designsystem.NatureScene
import me.remember.app.core.designsystem.RememberMeBrand
import me.remember.app.core.designsystem.atmosphere
import me.remember.app.core.designsystem.LocalSimpleMode
import org.json.JSONObject

@Composable
fun NativeWorkbenchScreen(model: NativeWorkbenchModel, appearance: AppearanceChoice = AppearanceChoice(), updateAppearance: (AppearanceChoice) -> Unit = {}) {
    val state by model.ui.collectAsStateWithLifecycle()
    val call by model.voiceCall.collectAsStateWithLifecycle()
    if(call!=null){
        CompositionLocalProvider(LocalInteractions provides InteractionContext(reduceMotion=appearance.reduceMotion)) {
            VoiceCallScreen(call!!,model::endVoice)
        }
        return
    }
    CompositionLocalProvider(LocalInteractions provides InteractionContext(
        identity = "${state.actor}:${state.subject}", operation = state.operation,
        latest = { model.ui.value.operation }, reduceMotion = appearance.reduceMotion,
    )) {
        NativeWorkbenchContent(model, appearance, updateAppearance, state)
    }
}

@Composable private fun NativeWorkbenchContent(model: NativeWorkbenchModel, appearance: AppearanceChoice,
    updateAppearance: (AppearanceChoice) -> Unit, state: NativeState) {
    val localPlayer by model.audio.playback.collectAsStateWithLifecycle()
    var server by remember { mutableStateOf(me.remember.app.BuildConfig.SERVICE_URL) }
    LaunchedEffect(server, state.actor) { if(state.actor.isBlank()) model.loadServiceInfo(server) }
    var token by remember { mutableStateOf("") }
    var tab by rememberSaveable(state.actor, state.subject) { mutableIntStateOf(0) }
    var archiveMode by rememberSaveable(state.actor, state.subject) { mutableIntStateOf(if(appearance.simpleMode) 3 else 1) }
    var lastSimpleMode by rememberSaveable { mutableStateOf(appearance.simpleMode) }
    LaunchedEffect(appearance.simpleMode) {
        if(lastSimpleMode != appearance.simpleMode) {
            archiveMode = if(appearance.simpleMode) 3 else 1
            lastSimpleMode = appearance.simpleMode
        }
    }
    var gardenStoryOpen by remember(state.actor, state.subject) { mutableStateOf(false) }
    val pages = rememberSaveableStateHolder()
    val identity = "${state.actor}:${state.subject}"
    var previousIdentity by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(identity) {
        previousIdentity?.takeIf { it != identity }?.let { old -> pages.removeState("archive:$old"); pages.removeState("settings:$old") }
        previousIdentity = identity
    }
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    var detail by remember(state.actor, state.subject) { mutableStateOf<String?>(null) }
    var askDraft by rememberSaveable(state.actor,state.subject) { mutableStateOf("") }
    var recordingPage by rememberSaveable(state.actor,state.subject) { mutableStateOf(false) }
    var revision by remember(state.actor, state.subject) { mutableStateOf<RevisionTarget?>(null) }
    var confirm by remember(state.actor, state.subject) { mutableStateOf<ActionConfirmation?>(null) }
    val gardenVisible = state.actor.isNotBlank() && tab == 1 && archiveMode == 1 && !state.recording
    val view = LocalView.current
    val darkBars = gardenVisible || MaterialTheme.colorScheme.background.luminance() < .5f
    val barColor = if(gardenVisible) gardenGlass else MaterialTheme.colorScheme.background
    SideEffect {
        val activity = generateSequence(view.context) { (it as? ContextWrapper)?.baseContext }
            .filterIsInstance<Activity>().firstOrNull()
        activity?.window?.let { window ->
            // Reapply after activity/session restoration; some window recreations
            // restore opaque system bars independently of their icon appearance.
            WindowCompat.setDecorFitsSystemWindows(window, false)
            @Suppress("DEPRECATION")
            run { window.statusBarColor = barColor.toArgb(); window.navigationBarColor = barColor.toArgb() }
            WindowCompat.getInsetsController(window, view).apply {
            isAppearanceLightStatusBars = !darkBars
            isAppearanceLightNavigationBars = !darkBars
        } }
    }
    val scene = appearance.scene.scene ?: if(gardenVisible) NatureScene.Meadow else when(tab) { 1 -> NatureScene.Forest; 2 -> NatureScene.Lake; 3 -> NatureScene.Coast; else -> NatureScene.Meadow }
    val backdrop = if(gardenVisible) Modifier.reviewedGardenAtmosphere(scene)
        else if(appearance.simpleMode) Modifier.background(MaterialTheme.colorScheme.background) else Modifier.atmosphere(scene = scene)
    val ready = !state.busy && !state.recording
    val scrollPositions = List(4) { rememberScrollState() }
    LaunchedEffect(state.captureFocusRequest) {
        if(state.captureFocusRequest.isNotBlank() && state.owner) {
            focus.clearFocus();keyboard?.hide();tab=0;detail=null
            scrollPositions[0].scrollTo(0)
        }
    }
    // Register before child handlers so flower/petal and settings Back keep priority.
    BackHandler(appearance.simpleMode && tab != 0) {
        if(tab == 1 && archiveMode != 3) { archiveMode = 3; scope.launch { scrollPositions[1].scrollTo(0) } }
        else tab = 0
    }
    BackHandler(state.companionRecording.isNotBlank()) { model.finishCompanionRecording() }
    BackHandler(state.recording && state.calibrationId.isNotBlank() && state.companionRecording.isBlank()) { model.finish() }
    if(recordingPage && state.owner) {
        StoryRecordingFlow(state,model,revision,{revision=it},
            {revision=null;recordingPage=false},{recordingPage=false;tab=0})
        return
    }
    Scaffold(modifier = backdrop, containerColor = androidx.compose.ui.graphics.Color.Transparent, bottomBar = {
        if(state.actor.isNotBlank() && !state.recording) NavigationBar(Modifier.padding(horizontal = 16.dp, vertical = 8.dp).clip(RoundedCornerShape(28.dp)), containerColor = if(gardenVisible) gardenGlass.copy(alpha = .94f) else MaterialTheme.colorScheme.surface.copy(alpha = .94f)) {
            (if(appearance.simpleMode) listOf("今天", "故事", "问答", "我的") else listOf("今天", "档案", "对话", "我的")).forEachIndexed { index, title ->
                NavigationBarItem(selected = tab == index, onClick = { focus.clearFocus(); keyboard?.hide(); tab = index }, icon = {
                    Icon(listOf(Icons.Outlined.WbSunny, Icons.Outlined.FolderOpen, Icons.Outlined.ChatBubbleOutline, Icons.Outlined.PersonOutline)[index], title)
                }, label = { Text(title) }, colors = if(gardenVisible) NavigationBarItemDefaults.colors(
                    selectedIconColor = gardenInk, selectedTextColor = gardenInk,
                    unselectedIconColor = gardenMuted, unselectedTextColor = gardenMuted,
                    indicatorColor = gardenMuted.copy(alpha = .17f)) else NavigationBarItemDefaults.colors())
            }
        }
    }) { inset ->
        Column(Modifier.fillMaxSize().padding(inset).padding(horizontal = 16.dp)) {
            Row(Modifier.fillMaxWidth().padding(vertical = if(gardenVisible) 8.dp else 12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                RememberMeBrand(size = 30.dp, darkBackground = gardenVisible || MaterialTheme.colorScheme.background.luminance() < .5f)
                if(!appearance.simpleMode) Text("勿忘我", style = MaterialTheme.typography.titleMedium, color = if(gardenVisible) gardenInk else MaterialTheme.colorScheme.onBackground)
                Spacer(Modifier.weight(1f))
                if(state.actor.isNotBlank()) SpaceChooser(state, model, gardenVisible, ready, Modifier.weight(2.4f))
            }
            key(identity) { RememberLoadingSlot(state.busy) }
            state.error?.let { message -> RememberIssue(message) { model.dismissError(message) } }
            if(state.actor.isBlank()) {
                Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    var username by remember { mutableStateOf("") }
                    var password by remember { mutableStateOf("") }
                    var name by remember { mutableStateOf("") }
                    var registering by remember { mutableStateOf(false) }
                    var connection by remember { mutableStateOf(false) }
                    Text("进入自己的空间", style = MaterialTheme.typography.headlineMedium)
                    Text("留住想记得的故事，也决定与谁分享。")
                    if(state.connectionCheck.message.isNotBlank()) Text(state.connectionCheck.message, style = MaterialTheme.typography.bodySmall)
                    TextButton(onClick = { model.loadServiceInfo(server) }, enabled = !state.busy && state.connectionCheck.phase != ConnectionPhase.CHECKING) { Text("检查连接") }
                    OutlinedTextField(username, { username = it }, label = { Text("账号") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    OutlinedTextField(password, { password = it }, label = { Text("密码（至少8个字符）") }, modifier = Modifier.fillMaxWidth(), singleLine = true, visualTransformation = PasswordVisualTransformation())
                    if(registering) OutlinedTextField(name, { name = it }, label = { Text("怎么称呼你") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                    RememberActionButton(if(registering) "创建我的空间" else "登录",
                        enabled = !state.busy && username.isNotBlank() && password.length >= 8 && (!registering || name.isNotBlank()),
                        filled=true, pendingLabel="正在进入…", successLabel="已连接") {
                        model.signIn(server, username, password, if(registering) name else null)
                    }
                    LaunchedEffect(state.serviceInfo.registrationAllowed) { if(!state.serviceInfo.registrationAllowed) registering = false }
                    if(state.serviceInfo.registrationAllowed) TextButton(onClick = { registering = !registering }) { Text(if(registering) "已有账号，返回登录" else "第一次使用，创建账号") }
                    else Text("本次内测由管理员准备账号；亲友使用自己的账号领取邀请。", style = MaterialTheme.typography.bodySmall)
                    Text("登录状态加密保存在设备上。退出会清除本机访问内容。", style = MaterialTheme.typography.bodySmall)
                    if(me.remember.app.BuildConfig.DEBUG) TextButton(onClick = { connection = !connection }) { Text(if(connection) "收起连接设置" else "连接设置 / 开发身份") }
                    if(connection && me.remember.app.BuildConfig.DEBUG) {
                    OutlinedTextField(server, { server = it }, label = { Text("共享后端地址") }, modifier = Modifier.fillMaxWidth(), singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
                    OutlinedTextField(token, { token = it }, label = { Text("身份凭据") }, modifier = Modifier.fillMaxWidth(), singleLine = true,
                        visualTransformation = PasswordVisualTransformation())
                    Button(onClick = { model.connect(server, token); token = "" }, enabled = !state.busy && token.isNotBlank()) { Text("进入空间") }
                    Text("云端演示使用预设 HTTPS 地址直接连接，无需电脑转发。连接本机开发服务时才需要局域网或 ADB；HTTP 仅支持本机或私有局域网。", style = MaterialTheme.typography.bodySmall)
                    Text("每日提醒：关闭。录音、上传和云端文字处理均由你主动发起。", style = MaterialTheme.typography.bodySmall)
                    }
                }
            } else {
                if(state.subject.isBlank()) {
                    Text(if(state.spaceChoiceRequired) "请选择要进入的空间。" else "还没有可进入的空间。可以请记录者授权故事。")
                    TextButton(onClick = model::logout, enabled = !state.busy) { Text("退出身份") }
                }
                if(tab == 0 && !appearance.simpleMode) Text(if(state.owner) "把这一刻留下来" else "听听${state.space?.text("display_name").orEmpty()}留下的故事。", style = MaterialTheme.typography.headlineMedium)
                if(state.notice.isNotBlank() && tab!=0 && (tab!=1 || archiveMode==0)) Text(state.notice, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onBackground, modifier = Modifier.padding(vertical = 8.dp))
                if(appearance.simpleMode) SimpleSourcePlayer(state, model)
                else if(state.player.episode.isNotBlank()) GardenMiniPlayer(state.player,
                    {if(state.player.playing) model.pauseSource() else model.resumeSource()},model::seekSource,model::stopSource)
                if(localPlayer.audioPath != null) Panel {
                    Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                        Text("原音 ${clock(localPlayer.positionMillis)} / ${clock(localPlayer.durationMillis)}",modifier=Modifier.weight(1f),style=MaterialTheme.typography.bodyMedium)
                        IconButton(onClick={if(localPlayer.playing) model.audio.pausePlayback() else model.audio.resumePlayback()}) { Icon(if(localPlayer.playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,if(localPlayer.playing) "暂停原音" else "播放原音") }
                        IconButton(onClick=model.audio::stopPlayback) { Icon(Icons.Outlined.Close,"关闭原音") }
                    }
                    RememberAudioScrubber("$identity:${localPlayer.audioPath}",localPlayer.positionMillis,localPlayer.durationMillis,
                        enabled=!localPlayer.preparing,seek=model.audio::seekPlayback)
                }
                if(state.subject.isNotBlank()) {
                    Column(Modifier.weight(1f).clipToBounds().rememberPageEntrance("$identity:$tab").then(if(tab==1 && archiveMode==2) Modifier else Modifier.verticalScroll(scrollPositions[tab])).padding(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        when(tab) {
                            0 -> {
                                if(appearance.simpleMode && !state.owner) SimpleHome(state, {revision=null;recordingPage=true},
                                    {tab=1;archiveMode=3}, {tab=1;archiveMode=0}, {tab=2})
                                else if(state.owner) TodayStoryScreen(state,model,{revision=null;recordingPage=true},
                                    {tab=1;archiveMode=0},{detail=it}, onStageChanged={
                                        focus.clearFocus();keyboard?.hide();scope.launch {scrollPositions[0].animateScrollTo(0)}
                                    })
                                else {
                                    Text("从真实故事和声音，了解这个人。")
                                    if(state.stories.isEmpty()) Text("这里暂时没有可见故事。")
                                    state.stories.take(3).forEach { story -> StoryCard(story, false, ready,
                                        { detail = story.text("episode_id") }, {}, {}) }
                                    Action("进入花田", ready) { tab = 1; archiveMode = 1 }
                                    Action("提出一个问题", ready) { tab = 2 }
                                }
                            }
                            1 -> pages.SaveableStateProvider("archive:$identity") {
                                if(appearance.simpleMode && archiveMode!=3 && (!gardenVisible || !gardenStoryOpen)) TextButton(onClick={archiveMode=3;scope.launch { scrollPositions[1].scrollTo(0) }}, modifier=Modifier.heightIn(min=60.dp)) {
                                    Icon(Icons.Outlined.ArrowBack,null); Spacer(Modifier.width(8.dp)); Text("返回故事列表")
                                }
                                if(!appearance.simpleMode && (!gardenVisible || !gardenStoryOpen)) Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp),verticalAlignment=Alignment.CenterVertically) {
                                    listOf(1 to "花田", 2 to "人物", 4 to "亲友").forEach { (index,title) -> FilterChip(archiveMode==index,{focus.clearFocus();archiveMode=index;scope.launch { scrollPositions[1].scrollTo(0) }},label={Text(title)},enabled=ready,
                                        colors=if(gardenVisible) FilterChipDefaults.filterChipColors(labelColor=gardenInk,selectedLabelColor=gardenGlass,selectedContainerColor=gardenInk) else FilterChipDefaults.filterChipColors()) }
                                    Spacer(Modifier.weight(1f))
                                    TextButton(onClick={focus.clearFocus();archiveMode=0;scope.launch { scrollPositions[1].scrollTo(0) }},enabled=ready) { Text("全部录音",color=if(gardenVisible) gardenInk else MaterialTheme.colorScheme.primary) }
                                }
                                if(archiveMode==0) {
                                    Text("我的录音",style=MaterialTheme.typography.headlineMedium)
                                    if(appearance.simpleMode && state.owner) Text("声音已经保存，可以先听，也可以稍后整理。",style=MaterialTheme.typography.bodyLarge)
                                    if(state.owner) CaptureTab(state,model,revision,{revision=it})
                                    state.stories.forEach { story -> StoryCard(story,state.owner,ready,
                                        {detail=story.text("episode_id")},{model.review(story.text("episode_id"))},
                                        {model.retry(story.text("episode_id"),story.optBoolean("can_reextract_empty"))}) }
                                }
                                if(archiveMode == 3) SimpleStories(state, model, {detail=it},
                                    {archiveMode=1;scope.launch {scrollPositions[1].scrollTo(0)}},
                                    {archiveMode=2;scope.launch {scrollPositions[1].scrollTo(0)}},
                                    {archiveMode=0;scope.launch {scrollPositions[1].scrollTo(0)}})
                                if(archiveMode == 1) MemoryGardenScreen(state, model, appearance, updateAppearance, scrollPositions[1],
                                    { detail = it }, { archiveMode = 2; scope.launch { scrollPositions[1].scrollTo(0) } },
                                    { archiveMode = 0; scope.launch { scrollPositions[1].scrollTo(0) } }, ask={askDraft=it;tab=2}, onStoryOpenChanged = { gardenStoryOpen = it })
                                if(archiveMode == 2) NarrativeScreen(state, model, Modifier.weight(1f)) { detail = it }
                                if(appearance.simpleMode && archiveMode!=4) TextButton(onClick={archiveMode=4}) { Text("亲友补记与留给你的信") }
                                if(archiveMode == 4) CompanionScreen(state,model)
                            }
                            2 -> AskTab(state, model,askDraft) { tab=1;archiveMode=2 }
                            3 -> pages.SaveableStateProvider("settings:$identity") {
                                AppSettingsScreen(state, model, appearance, updateAppearance,
                                    { tab = 1; archiveMode = 2 }, { tab = 1; archiveMode = 0 },
                                    { scope.launch { scrollPositions[3].scrollTo(0) } }) { message, destructive, action -> confirm = ActionConfirmation(message, destructive, action) }
                            }
                        }
                        if(tab!=1 || archiveMode!=2) Spacer(Modifier.height(28.dp))
                    }
                }
            }
        }
    }
    if(state.spaceChoiceRequired) AlertDialog(onDismissRequest={}, title={Text("想进入谁的空间？")},
        containerColor=if(MaterialTheme.colorScheme.background.luminance()<.5f) androidx.compose.ui.graphics.Color(0xFF263C32) else androidx.compose.ui.graphics.Color(0xFFF5F3E8),
        text={Column(Modifier.heightIn(max=420.dp).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            state.spaces.forEach { space -> OutlinedButton(onClick={model.selectSpace(space)},enabled=ready,
                modifier=Modifier.fillMaxWidth().testTag("choose-space-${space.text("subject_id")}")) {
                Column { Text(space.text("display_name"));Text(if(space.text("role")=="owner") "我的空间 · 记录与管理" else "亲友空间 · 获授权阅读",style=MaterialTheme.typography.bodySmall) }
            } }
        }},confirmButton={TextButton(onClick=model::logout,enabled=ready){Text("退出账号")}})
    detail?.let { id ->
        state.stories.firstOrNull { it.text("episode_id") == id }?.let { story ->
            NativeDialog("故事与来源", { detail = null }) {
                Text(recordingDate(story.text("recorded_at")), style = MaterialTheme.typography.bodySmall)
                if(story.optBoolean("unavailable")) Text(story.text("notice")) else {
                    var showRawTranscript by remember(id) { mutableStateOf(false) }
                    Action("播放完整原音", ready) { detail = null; model.playSource(id) }
                    Text(if(story.optBoolean("waiting_for_review")) "机器转写 · 尚未核对" else "核对文字", style = MaterialTheme.typography.titleMedium)
                    Text(story.text("transcript").ifBlank { "转写尚未完成。" })
                    if(state.owner && story.text("machine_transcript").isNotBlank()) {
                        TextButton(onClick = { showRawTranscript = !showRawTranscript }) {
                            Text(if(showRawTranscript) "收起机器原始输出" else "查看机器原始输出（保留原始字形）")
                        }
                        if(showRawTranscript) Text(story.text("machine_transcript"))
                    }
                    story.rows("memories").forEach { memory -> Panel {
                        Text(memory.text("content"))
                        Text(if(memory.text("origin") == "owner_supplement") "本人书面补充 · 不属于录音原话" else "系统整理 · ${memory.text("source_type")} · ${memory.text("review_state")}", style = MaterialTheme.typography.bodySmall)
                        memory.rows("evidence").forEach { evidence -> Text("依据：${evidence.text("excerpt")}", style = MaterialTheme.typography.bodySmall) }
                        if(state.owner && memory.text("review_state") == "active") {
                            Action("用新录音补充、纠正或说明变化", ready) {
                                revision = RevisionTarget(memory.text("memory_item_id"), "supplement", ""); detail = null; tab = 0; recordingPage = true
                            }
                            Action("删除这条记忆", ready) {
                                confirm = ActionConfirmation("删除这条记忆并使相关回答失效？完整原音和核对文字会保留。", true) {
                                    detail = null; model.mutation("/memories/${segment(memory.text("memory_item_id"))}", "DELETE", subjectApi = true)
                                }
                            }
                        }
                    } }
                }
            }
        }
    }
    state.reviewEpisode?.let { id ->
        val leaveReview: () -> Unit = model::closeReview
        NativeDialog("看看这段文字", leaveReview) {
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            val correction = state.reviewCorrection
            RecordingHighlights(state.reviewHighlights,state.reviewText != state.reviewInitialText)
            val changes = correction?.rows("edits").orEmpty()
            var showChanges by remember(id) { mutableStateOf(false) }
            if(correction?.text("status") == "completed") {
                val applied = changes.count { it.text("action") == "auto" }
                val uncertain = changes.size - applied
                Text(if(state.reviewText == state.reviewInitialText)
                    (if(applied > 0) "已自动修订 $applied 处" else "已检查转写文字")
                    else if(state.reviewText == state.reviewMachineText) "当前为机器原稿" else "当前为你修改的文字")
                if(uncertain > 0) Text("有 $uncertain 处拿不准，可以听听原音。")
                if(changes.isNotEmpty()) Action(if(showChanges) "收起修改" else "查看修改") { showChanges = !showChanges }
                if(showChanges) changes.forEach { change ->
                    Text(if(change.text("action") == "auto") "${change.text("before")} → ${change.text("after")}"
                        else "待确认：${change.text("before")}（${change.text("reason")}）")
                }
                if(showChanges && state.reviewMachineText.isNotBlank()) {
                    Action("恢复机器稿", ready) { model.editReview(id, state.reviewMachineText) }
                    Action("恢复自动修订稿", ready) { model.editReview(id, state.reviewInitialText) }
                }
            } else if(correction != null) Text(when(correction.text("status")) {
                "too_long" -> "这段较长，暂未自动纠错，已保留原稿。"
                "unavailable" -> "本次未采用自动修订，已保留原稿。"
                else -> "自动纠错未成功，已保留原稿。"
            })
            state.reviewWarnings.forEach { Text(it, color = MaterialTheme.colorScheme.error) }
            if(state.reviewParagraphPreview != null) {
                Text("可以采用识别服务的分段，仅调整换行，仍需听音核对。", style = MaterialTheme.typography.bodySmall)
                Action("采用分段排版", state.reviewText == state.reviewInitialText) { model.useParagraphPreview() }
            }
            Action("播放原音", ready) { model.playSource(id) }
            if(state.player.episode == id) {
                Text("${clock(state.player.position)} / ${clock(state.player.duration)}")
                if(!state.player.preparing) {
                    RememberAudioScrubber("$identity:$id",state.player.position,state.player.duration,
                        enabled=!state.recording,seek=model::seekSource)
                    Action(if(state.player.playing) "暂停核对原音" else "继续核对原音") { if(state.player.playing) model.pauseSource() else model.resumeSource() }
                }
                Action("停止核对原音") { model.stopSource() }
            }
            OutlinedTextField(state.reviewText, { model.editReview(id, it) }, label = { Text("核对后的文字") }, modifier = Modifier.fillMaxWidth(), minLines = 6)
            OutlinedTextField(state.reviewSupplement, model::editSupplement, label = { Text("本次补充说明（选填）") }, placeholder = { Text("例如：这里的老隗是同事隗师傅；方言‘落屋’指回家。") }, modifier = Modifier.fillMaxWidth(), minLines = 3)
            if(state.vocabulary.isNotBlank()) Action("带入我的用词") { model.editSupplement(listOf(state.reviewSupplement, state.vocabulary).filter { it.isNotBlank() }.joinToString("\n")) }
            RememberActionButton("保存到记忆", ready && state.reviewText.isNotBlank(), filled=true,
                pendingLabel="正在保存…", successLabel="已保存") { model.confirmReview(state.reviewText, true) }
            if(appearance.simpleMode) TextButton(onClick=leaveReview,modifier=Modifier.heightIn(min=60.dp)) {Text("稍后再核对")}
        }
    }
    confirm?.let { request -> RememberConfirmationDialog(request.message, request.destructive, ready,
        dismiss = { confirm = null }, confirm = { confirm = null; request.action() }) }
}

@Composable internal fun CaptureTab(state: NativeState, model: NativeWorkbenchModel, revision: RevisionTarget?, setRevision: (RevisionTarget?) -> Unit) {
    if(!state.owner) { Text("这里可以查看记录者授权的故事。你也可以在管理页提出想了解的问题。"); return }
    val resolver = LocalContext.current.contentResolver
    var exportTicket by rememberSaveable(state.actor, state.subject) { mutableStateOf<String?>(null) }
    var importTicket by rememberSaveable(state.actor, state.subject) { mutableStateOf<String?>(null) }
    val exportAudio = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("audio/mp4")) { uri ->
        exportTicket?.let { id -> if(uri == null) model.cancelCaptureTransfer(id) else model.exportOriginal(id) { resolver.openOutputStream(uri) } }
        exportTicket = null
    }
    val importDraft = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        importTicket?.let { id -> if(uri == null) model.cancelCaptureTransfer(id) else model.importTranscript(id) { resolver.openInputStream(uri) } }
        importTicket = null
    }
    val pending=state.local.filter { !it.linked }
    if(pending.isNotEmpty()) Text("待处理录音",style=MaterialTheme.typography.titleMedium)
    pending.forEach { capture -> Panel {
        val caps = state.asrCapabilities
        val clientAsr = capture.usesClientTranscript(caps?.text("stt") == "client")
        Text(recordingDate(capture.recording.createdAt) + " · " + clock(capture.recording.durationMillis))
        Text(if(capture.source == "WORK_3200") "来源：录音豆" else if(capture.source == "IMPORT") "来源：导入" else "来源：手机录音", style = MaterialTheme.typography.labelMedium)
        if(state.uploadKey == capture.key) {
            Text(state.uploadPercent?.let { if(it == 100) "原音已发送，等待服务器确认…" else "上传原音 $it%" } ?: "准备上传…")
            state.uploadPercent?.let { percent -> LinearProgressIndicator(progress = { percent / 100f }, modifier = Modifier.fillMaxWidth()) }
        }
        Text(if(capture.episode.isBlank()) "尚未上传" else if(!capture.linked) "已上传，关联未完成，请重试" else "已上传", style = MaterialTheme.typography.bodySmall)
        capture.revision?.let { Text("${kindName(it.kind)}旧记忆；关联完成后才可确认转写。", style = MaterialTheme.typography.bodySmall) }
        Action("播放本机原音", !state.busy && !state.recording) { model.playLocal(capture) }
        if(clientAsr && !capture.linked) {
            Text("当前演示由电脑接力转写：导出原音，经转写工具处理后取回 JSON 机器稿。手机会核验它是否对应这段录音。", style = MaterialTheme.typography.bodySmall)
            Action("导出这段原音", !state.busy && !state.recording) {
                model.beginCaptureTransfer(capture, importing = false)?.let { id ->
                    exportTicket = id; exportAudio.launch("${capture.key}.m4a")
                }
            }
            Action(if(capture.transcript == null) "取回机器转写" else "重新选择机器稿", !state.busy && !state.recording && !capture.uploadAttempted && capture.episode.isBlank()) {
                model.beginCaptureTransfer(capture, importing = true)?.let { id ->
                    importTicket = id; importDraft.launch(arrayOf("application/json", "text/plain"))
                }
            }
            if(capture.transcript != null) Text("机器稿已匹配原音，尚未本人核对。", style = MaterialTheme.typography.labelMedium)
            if(capture.uploadAttempted) Text("已开始上传，重试沿用同一份机器稿；识别错误可在核对页修改。", style = MaterialTheme.typography.bodySmall)
        }
        if(!capture.linked) {
            val configured = caps != null && (clientAsr || caps.text("stt_processing") != "cloud" || caps.optBoolean("stt_configured")) &&
                (!clientAsr || capture.transcript != null || capture.episode.isNotBlank())
            if(!configured) Text(if(clientAsr) "取回机器转写后即可上传，原音仍保留本机。" else "转写连接配置未完成，原音仍保留本机。")
            val error=state.captureErrors[capture.key]
            if(capture.autoProcess && error==null) Text("自动转写中…")
            else RememberActionButton(if(capture.episode.isBlank()) "转成文字" else "重试上传与关联", configured && !state.busy && !state.recording,
                filled=true, pendingLabel="正在上传原音…", successLabel="已提交识别") { model.upload(capture, true) }
        }
    } }
}

@Composable private fun StoryCard(story: JSONObject, owner: Boolean, enabled: Boolean, open: () -> Unit, review: () -> Unit, retry: () -> Unit) = Panel {
    Text(storyTitle(story), style = MaterialTheme.typography.titleMedium)
    Text(recordingDate(story.text("recorded_at")) + " · " + if(story.optBoolean("waiting_for_review")) "待核对文字" else processingLabel(story.text("status")), style = MaterialTheme.typography.bodySmall)
    if(story.text("error_message").isNotBlank()) Text(story.text("error_message"), color = MaterialTheme.colorScheme.error)
    if(story.optBoolean("unavailable")) Text(story.text("notice")) else {
        Action("打开故事", enabled, open)
        if(owner && !story.optBoolean("reviewed")) Action("核对转写", enabled, review)
        if(owner && story.text("status") == "failed") Action("重试处理", enabled, retry)
        if(owner && story.optBoolean("can_reextract_empty")) Action("未提取到记忆，重新整理", enabled, retry)
    }
}

@Composable internal fun AskTab(state: NativeState, model: NativeWorkbenchModel, initialQuestion:String="", openPerson: () -> Unit = {}) {
    val focus = androidx.compose.ui.platform.LocalFocusManager.current
    val keyboard = androidx.compose.ui.platform.LocalSoftwareKeyboardController.current
    var question by rememberSaveable(state.actor, state.subject, initialQuestion) { mutableStateOf(initialQuestion) }
    var cloud by remember(state.actor, state.subject) { mutableStateOf(false) }
    var mode by rememberSaveable(state.actor,state.subject) { mutableStateOf("evidence") }
    var sources by remember(state.answer?.text("answer_id")) { mutableStateOf(false) }
    var tools by rememberSaveable(state.actor,state.subject) { mutableStateOf(false) }
    val style=state.narrative.optJSONObject("style")
    Text("聊一聊", style = MaterialTheme.typography.headlineMedium)
    VoiceCallEntry(state,model,mode)
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
        FilterChip(mode=="evidence",{mode="evidence"},label={Text("查找记录")})
        FilterChip(mode=="persona",{mode="persona"},enabled=style?.optBoolean("enabled")==true,label={Text("与 AI 分身聊聊")})
    }
    LaunchedEffect(style?.optBoolean("enabled")) { if(style?.optBoolean("enabled")!=true) mode="evidence" }
    OutlinedTextField(question, { question = it }, label = { Text("想了解什么？") }, modifier = Modifier.fillMaxWidth(), minLines = 2)

    Check("同意将问题与已授权的核对文字交由云端回答", cloud, { cloud = it })
    RememberActionButton("提问", !state.busy && !state.recording && question.isNotBlank() && cloud, filled=true,
        icon=Icons.Outlined.ChatBubbleOutline, pendingLabel="正在整理回答…", successLabel="回答已返回") {
        focus.clearFocus(); keyboard?.hide(); model.ask(question, cloud, mode)
    }
    if(state.owner) TextButton(onClick={tools=!tools}) { Text(if(tools) "收起对话工具" else "对话工具") }
    if(state.owner && tools) {
    if(style!=null) RememberToggle("允许分身使用已确认的理解与表达",style.optBoolean("enabled"),{enabled -> model.mutation("/narrative/style","PUT",JSONObject().put("revision",style.optInt("revision")).put("enabled",enabled))},enabled=!state.busy&&!state.recording)
    RememberActionButton("先录下我的回答，再对照",!state.busy&&!state.recording&&question.isNotBlank()&&cloud,
        pendingLabel="正在准备问题…",successLabel="可以开始回答"){
        focus.clearFocus();keyboard?.hide();model.prepareVoiceCalibration(question,mode)
    }
    }
    state.answer?.let { answer -> Panel {
        Text(if(answer.text("mode")=="persona") "AI 分身" else when(answer.text("response_type")) { "ORIGINAL" -> "来自本人原话"; "SIMULATION" -> "AI 分身"; else -> "还没有足够的记录" }, style = MaterialTheme.typography.titleMedium)
        Text(answer.text("answer"),style=MaterialTheme.typography.bodyLarge)
        personaCoverageHint(answer)?.let {Text(it,style=MaterialTheme.typography.bodyMedium)}
        if(answer.text("response_type")!="UNKNOWN") RememberActionButton("听这条回答", !state.busy,
            pendingLabel="正在准备声音…",successLabel="声音已取回") { model.speakAnswer(answer) }
        if(state.owner && tools && answer.text("response_type")!="UNKNOWN") {
            var compareCloud by remember(answer.text("answer_id")) { mutableStateOf(false) }
            Check("同意将两段回答交由云端比较",compareCloud,{compareCloud=it})
            RememberActionButton("和我的想法对照",!state.busy&&!state.recording&&compareCloud,
                pendingLabel="正在保存这次问题…",successLabel="对照已开始") {model.startCalibration(answer,compareCloud)}
        }
        TextButton(onClick={sources=!sources}) { Text(if(sources) "收起依据" else "查看理解与来源") }
        if(sources) {
            val ids=answer.optJSONArray("understanding_ids")?.let {a->(0 until a.length()).map{a.getString(it)}}.orEmpty()
            confirmedUnderstandings(state.narrative).filter{it.text("candidate_id") in ids}.forEach {Text(it.text("statement"));Text("适用情境："+it.text("context"))}
            answer.rows("evidence").forEach { evidence -> Evidence(evidence, state, model) }
            val contributions=answer.optJSONArray("contribution_ids")?.let{a->(0 until a.length()).map{a.getString(it)}}.orEmpty()
            state.companion.rows("contributions").filter{it.text("id") in contributions}.forEach {Text(it.text("author_display_name")+"的补记："+it.text("text"))}
        }
    } }
    if(state.owner && (tools || state.calibrationId.isNotBlank())) CalibrationSection(state,model,openPerson)
    if(state.owner && tools) {
        var voiceSettings by remember { mutableStateOf(false) }
        var voiceConsent by remember(state.subject) { mutableStateOf(false) }
        TextButton(onClick={voiceSettings=!voiceSettings}) { Text("分身声音与亲友许可") }
        if(voiceSettings) Panel {
            if(!state.voiceProfile.optBoolean("ready") && state.voiceProfile.optJSONArray("synthetic_presets")?.length()?.let{it>0}==true) {
                Check("同意为这个虚构空间启用分身声音",voiceConsent,{voiceConsent=it})
                RememberActionButton("启用分身声音",!state.busy&&voiceConsent,pendingLabel="正在启用…",successLabel="已启用") {model.enrollSyntheticVoice(voiceConsent)}
            }
            Text(if(state.voiceProfile.optBoolean("ready")) "分身声音已就绪" else "分身声音尚未启用")
            if(state.voiceProfile.optBoolean("ready")) RememberConfirmedAction("停用分身声音","停用后，将不再生成或播放分身声音。",true,!state.busy,
                pendingLabel="正在停用…",successLabel="已停用") {model.disableVoice()}
            state.recipients.forEach { person ->
                val grant=state.voiceGrants.firstOrNull{it.text("actor_id")==person.text("actor_id")}
                key(person.text("actor_id")) {RememberToggle("允许${person.text("display_name")}收听分身回答",grant?.optBoolean("enabled")==true,
                    {model.voiceRecipient(person.text("actor_id"),it)},enabled=!state.busy&&!state.recording)}
            }
        }
    }
}
@Composable private fun Evidence(evidence: JSONObject, state: NativeState, model: NativeWorkbenchModel) {
    Text("依据：${evidence.text("excerpt")}")
    Text(if(evidence.text("source_type") == "CALIBRATION") "本人书面补充或修订 · 不是录音原话；原音供关联参考" else "来自核对后的讲述", style = MaterialTheme.typography.bodySmall)
    if(evidence.text("episode_id").isNotBlank()) Action("播放来源完整原音", !state.busy) { model.playSource(evidence.text("episode_id")) }
}

@Composable internal fun ManageTab(state: NativeState, model: NativeWorkbenchModel, confirm: ConfirmAction) {
    val enabled = !state.busy && !state.recording
    var requestText by remember(state.actor, state.subject) { mutableStateOf("") }
    Text("想了解的问题", style = MaterialTheme.typography.titleLarge)
    OutlinedTextField(requestText, { requestText = it }, label = { Text("请记录者补充讲述") }, modifier = Modifier.fillMaxWidth())
    Action("提交问题请求", enabled && requestText.isNotBlank()) { model.mutation("/requests", "POST", JSONObject().put("text", requestText.trim())); requestText = "" }
    state.requests.forEach { request -> Panel {
        Text(request.text("text")); Text("状态：${request.text("status")}", style = MaterialTheme.typography.bodySmall)
        if(state.owner) {
            Action("稍后再答", enabled) { model.mutation("/requests/${segment(request.text("request_id"))}", "PATCH", JSONObject().put("status", "snoozed")) }
            Action("暂不回答", enabled) { model.mutation("/requests/${segment(request.text("request_id"))}", "PATCH", JSONObject().put("status", "declined")) }
            Text("用已核对并整理完成的录音回答：", style = MaterialTheme.typography.bodySmall)
            state.stories.filter { it.text("status") == "ready" && it.optBoolean("reviewed") }.forEach { story ->
                Action(storyTitle(story), enabled) { model.mutation("/requests/${segment(request.text("request_id"))}", "PATCH", JSONObject().put("status", "answered").put("answer_episode_id", story.text("episode_id"))) }
            }
        }
        if(request.text("answer_episode_id").isNotBlank()) Action("听回答原音", enabled) { model.playSource(request.text("answer_episode_id")) }
    } }
    if(state.owner) {
        Text("核对修订关系", style = MaterialTheme.typography.titleLarge)
        state.revisions.forEach { revision -> Panel {
            val old = state.stories.flatMap { it.rows("memories") }.firstOrNull { it.text("memory_item_id") == revision.text("target_memory_id") }
            val next = state.stories.firstOrNull { it.text("episode_id") == revision.text("episode_id") }
            Text("${kindName(revision.text("kind"))} · ${revision.text("status")}")
            Text("原记忆：${old?.text("content") ?: "原记忆已变化"}")
            Text("新记忆：${next?.rows("memories")?.joinToString("；") { it.text("content") }?.ifBlank { "尚待整理" } ?: "尚待整理"}")
            if(revision.text("time_text").isNotBlank()) Text("变化时间：${revision.text("time_text")}")
            if(revision.text("status") == "pending") Action("确认这次关系", enabled && next?.text("status") == "ready") {
                confirm("确认新旧记忆的上述关系？纠正会使旧说法退出当前回答，原音继续保留。", false) { model.mutation("/revisions/${segment(revision.text("revision_id"))}/confirm", "POST") }
            }
        } }
        Text("人物理解候选", style = MaterialTheme.typography.titleLarge)
        Text("系统推断需要你确认，确认后仍是推断，不能当作本人原话。")
        var cloud by remember(state.subject) { mutableStateOf(false) }
        Check("同意将已核对文字交由云端归纳候选。", cloud, { cloud = it })
        Action("归纳人物候选", enabled && cloud) { model.refreshCandidates(cloud); cloud = false }
        state.candidateJobs.forEach { job -> Text("归纳任务：${job.text("status")} ${job.text("error")}", style = MaterialTheme.typography.bodySmall) }
        state.candidates.forEach { candidate -> Panel {
            Text(candidate.text("statement")); Text("${candidate.text("label")} · ${candidate.text("domain")} · ${candidate.text("status")}", style = MaterialTheme.typography.bodySmall)
            Text("${candidate.optInt("independent_episodes")} 段来源", style = MaterialTheme.typography.bodySmall)
            Text("重复说法不代表独立经历。", style = MaterialTheme.typography.bodySmall)
            Text("情境：${candidate.text("context")}")
            val evidenceIds = candidate.optJSONArray("evidence_ids")
            if(evidenceIds != null) for(i in 0 until evidenceIds.length()) {
                val evidenceId = evidenceIds.getString(i)
                val evidence = candidate.rows("evidence").firstOrNull { it.text("evidence_id") == evidenceId }
                    ?: state.stories.flatMap { it.rows("memories") }.flatMap { it.rows("evidence") }.firstOrNull { it.text("evidence_id") == evidenceId }
                if(evidence != null) Evidence(evidence, state, model) else Text("暂时无法打开这条依据。", style = MaterialTheme.typography.bodySmall)
            }
            Text("反证：${candidate.optJSONArray("counter_evidence_ids") ?: "[]"}", style = MaterialTheme.typography.bodySmall)
            if(candidate.text("status") == "pending") {
                var action by remember(candidate.text("candidate_id")) { mutableStateOf("ADD") }
                var target by remember(candidate.text("candidate_id")) { mutableStateOf("") }
                var reason by remember(candidate.text("candidate_id")) { mutableStateOf("") }
                var time by remember(candidate.text("candidate_id")) { mutableStateOf("") }
                listOf("ADD" to "新增理解", "SUPPORT" to "支持已有理解", "CONFLICT" to "与已有理解冲突", "CHANGE" to "随时间变化").forEach { (value, label) ->
                    Action((if(action == value) "已选：" else "") + label, enabled) { action = value }
                }
                if(action != "ADD") {
                    Text("请选择旧理解，并核对双方情境。过期理解必须重新验证来源。")
                    state.candidates.filter { it.text("candidate_id") != candidate.text("candidate_id") &&
                        it.text("stored_status") == "confirmed" && it.text("domain") == candidate.text("domain") && it.text("kind") == candidate.text("kind") }.forEach { old ->
                        Action((if(target == old.text("candidate_id")) "已选：" else "") + old.text("statement") + " · " + old.text("context"), enabled) { target = old.text("candidate_id") }
                    }
                }
                OutlinedTextField(value = reason, onValueChange = { reason = it.take(1000) }, label = { Text("关联理由") }, modifier = Modifier.fillMaxWidth())
                if(action == "CHANGE") OutlinedTextField(value = time, onValueChange = { time = it.take(200) }, label = { Text("变化时间，例如退休后") }, modifier = Modifier.fillMaxWidth())
                Action("保存为待确认更新", enabled && reason.isNotBlank() && (action == "ADD" || target.isNotBlank()) && (action != "CHANGE" || time.isNotBlank())) {
                    model.mutation("/profile-candidates/updates", "POST", JSONObject().put("candidate_id", candidate.text("candidate_id"))
                        .put("action", action).put("target_candidate_id", if(action == "ADD") JSONObject.NULL else target)
                        .put("reason", reason).put("time_text", if(action == "CHANGE") time else ""))
                }
                Action("拒绝此候选", enabled) { model.mutation("/profile-candidates/${segment(candidate.text("candidate_id"))}/reject", "POST") }
            }
            if(candidate.text("status") == "confirmed") Action("撤回这项确认", enabled) {
                confirm("撤回此候选的确认并使相关回答失效？", true) { model.mutation("/profile-candidates/${segment(candidate.text("candidate_id"))}/reject", "POST") }
            }
        } }
        state.profileUpdates.forEach { update -> Panel {
            val actions = mapOf("ADD" to "新增理解", "SUPPORT" to "支持已有理解", "CONFLICT" to "理解冲突", "CHANGE" to "随时间变化")
            Text("${actions[update.text("action")]} · ${update.text("status")}")
            state.candidates.firstOrNull { it.text("candidate_id") == update.text("candidate_id") }?.let { Text("新观察：${it.text("statement")}") }
            state.candidates.firstOrNull { it.text("candidate_id") == update.text("target_candidate_id") }?.let { Text("旧理解：${it.text("statement")}；情境：${it.text("context")}") }
            Text(update.text("reason"))
            if(update.text("time_text").isNotBlank()) Text("变化时间：${update.text("time_text")}")
            if(update.text("question").isNotBlank()) Text(update.text("question"))
            if(update.text("status") == "pending") {
                Action("确认上述更新", enabled) { confirm("已核对双方原文和情境？支持或变化保留历史；冲突暂停使用相关理解。", false) {
                    model.mutation("/profile-candidates/updates/${segment(update.text("update_id"))}/confirm", "POST")
                } }
                Action("拒绝这次更新", enabled) { model.mutation("/profile-candidates/updates/${segment(update.text("update_id"))}/reject", "POST") }
            }
        } }
    }
}

@Composable internal fun Panel(content: @Composable ColumnScope.() -> Unit) {
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface.copy(alpha = .95f))) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp), content = content) }
}
@Composable internal fun Action(label: String, enabled: Boolean = true, action: () -> Unit) {
    RememberActionButton(label, enabled, onClick = action)
}
@Composable internal fun Check(label: String, checked: Boolean, onChange: (Boolean) -> Unit, enabled: Boolean = true) {
    Row(Modifier.fillMaxWidth().heightIn(min=if(LocalSimpleMode.current) 60.dp else 48.dp)
        .toggleable(value=checked,enabled=enabled,role=Role.Checkbox,onValueChange=onChange),verticalAlignment=Alignment.CenterVertically) {
        Checkbox(checked, onCheckedChange = null, enabled = enabled); Text(label, Modifier.weight(1f).padding(vertical=12.dp))
    }
}
@Composable internal fun NativeDialog(title: String, close: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth().fillMaxHeight(.92f).padding(12.dp), shape = MaterialTheme.shapes.large) {
            if(LocalSimpleMode.current) Column(Modifier.fillMaxSize().padding(16.dp)) {
                Text(title,style=MaterialTheme.typography.titleLarge)
                OutlinedButton(onClick=close,modifier=Modifier.fillMaxWidth().heightIn(min=60.dp)) {Text("关闭")}
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(12.dp),content=content)
            } else Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                    Text(title,Modifier.weight(1f),style=MaterialTheme.typography.titleLarge)
                    TextButton(onClick=close) { Text("关闭") }
                }
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(12.dp),content=content)
            }
        }
    }
}
internal fun storyTitle(story: JSONObject): String = story.rows("memories").firstOrNull()?.text("content")?.take(34)
    ?: story.text("transcript").take(34).ifBlank { "一段新的记述" }
private fun kindName(kind: String) = when(kind) { "correction" -> "纠正"; "change" -> "情况变化"; else -> "补充" }
internal fun clock(ms: Long): String = "%02d:%02d".format(ms / 60_000, ms / 1000 % 60)

@Composable private fun SpaceChooser(state: NativeState, model: NativeWorkbenchModel, garden: Boolean, ready: Boolean, modifier: Modifier) {
    var expanded by remember(state.actor) { mutableStateOf(false) }
    val ink = if(garden) gardenInk else MaterialTheme.colorScheme.onSurface
    Box(modifier) {
        Surface(onClick={expanded=true}, enabled=ready, shape=RoundedCornerShape(20.dp),
            color=if(garden) gardenGlass.copy(alpha=.92f) else MaterialTheme.colorScheme.surface.copy(alpha=.92f),
            contentColor=ink, modifier=Modifier.fillMaxWidth().testTag("space-chooser")) {
            Row(Modifier.padding(horizontal=12.dp,vertical=7.dp),verticalAlignment=Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(state.space?.text("display_name") ?: "选择空间",style=MaterialTheme.typography.labelLarge,maxLines=1,overflow=TextOverflow.Ellipsis)
                    Text(if(state.owner) "我来记录" else "亲友阅读",style=MaterialTheme.typography.labelSmall,maxLines=1)
                }
                Icon(Icons.Outlined.ExpandMore,"切换人物空间",Modifier.size(20.dp))
            }
        }
        DropdownMenu(expanded,{expanded=false}) {
            Text("正在使用：${state.actorName}",Modifier.padding(16.dp),style=MaterialTheme.typography.labelMedium)
            state.spaces.forEach { space -> DropdownMenuItem(
                text={Column { Text(space.text("display_name")); Text(if(space.text("role")=="owner") "我的空间 · 记录与管理" else "亲友空间 · 获授权阅读",style=MaterialTheme.typography.bodySmall) }},
                modifier=Modifier.testTag("space-${space.text("subject_id")}"),
                onClick={expanded=false;model.selectSpace(space)}) }
        }
    }
}
