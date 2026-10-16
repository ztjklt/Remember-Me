package me.remember.app

import android.graphics.Bitmap
import android.media.AudioTrack
import android.media.AudioFormat
import android.media.AudioAttributes
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.core.view.WindowCompat
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.flow.MutableStateFlow
import me.remember.app.core.designsystem.*
import me.remember.app.data.repository.AndroidAudioCaptureService
import me.remember.app.integration.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Local production UI and protocol fixtures. No account, microphone, LLM or TTS request. */
class VoiceExperienceTest {
    @get:Rule val ui = createAndroidComposeRule<androidx.activity.ComponentActivity>()
    private fun show(fontScale: Float = 1f, content: @Composable () -> Unit) {
        ui.setContent { RememberMeTheme(darkTheme = true) {
            val density = LocalDensity.current
            val background = androidx.compose.material3.MaterialTheme.colorScheme.background
            SideEffect {
                @Suppress("DEPRECATION")
                run { ui.activity.window.statusBarColor = background.toArgb(); ui.activity.window.navigationBarColor = background.toArgb() }
                WindowCompat.getInsetsController(ui.activity.window, ui.activity.window.decorView).apply {
                    isAppearanceLightStatusBars = false; isAppearanceLightNavigationBars = false
                }
            }
            CompositionLocalProvider(LocalDensity provides Density(density.density, fontScale),
                LocalInteractions provides InteractionContext(reduceMotion = true)) { Surface { content() } }
        } }
    }
    private fun shot(name: String) {
        ui.waitForIdle(); Thread.sleep(400)
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        val folder = File(ui.activity.getExternalFilesDir(null), "voice-experience-review").apply { mkdirs() }
        File(folder, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
    @Test fun conversationPhasesAndInterruptRemainClear() {
        var state by mutableStateOf(CallUi(active = true, status = "正在连接"))
        var ended = 0
        show { VoiceCallContent(state, {
            state = state.copy(paused = !state.paused, phase = if(state.paused) CallPhase.LISTENING else CallPhase.PAUSED,
                status = if(state.paused) "我在听" else "已暂停")
        }, { state = state.copy(phase = CallPhase.LISTENING, status = "我在听", answer = "", sources = null) }, { ended++ }) }
        ui.onNodeWithText("暂停").assertIsNotEnabled()
        ui.runOnIdle { state = state.copy(ready = true, phase = CallPhase.LISTENING, status = "我在听") }
        shot("01-listening")
        ui.runOnIdle { state = state.copy(phase = CallPhase.THINKING, status = "正在想", transcript = "临时来了一个安排，我一般会怎么处理？") }
        ui.onNodeWithTag("voice-interrupt").assertIsDisplayed(); shot("02-thinking")
        ui.runOnIdle { state = state.copy(phase = CallPhase.PREPARING, status = "准备播报",
            answer = "平常我大概会先问清楚，再决定怎么安排。但家里有急事时，我可能会先顾家里。",
            sources = JSONObject().put("response_type", "SIMULATION")) }
        ui.onNodeWithText("准备播报").assertIsDisplayed()
        ui.runOnIdle { state = state.playbackStarted() }
        shot("03-speaking")
        ui.onNodeWithTag("voice-interrupt").performClick()
        assertEquals("", state.answer)
        ui.onNodeWithText("我在听").assertIsDisplayed()
        ui.onNodeWithText("暂停").performClick()
        ui.onNodeWithText("已暂停").assertIsDisplayed(); shot("04-paused")
        ui.onNodeWithText("继续").performClick()
        ui.onNodeWithText("我在听").assertIsDisplayed()
        ui.onNodeWithText("结束").performClick(); assertEquals(1, ended)
    }
    @Test fun transcriptAndEvidenceAreAvailableWithoutClutteringTheCall() {
        val answer = JSONObject().put("response_type", "ORIGINAL").put("evidence", org.json.JSONArray().put(JSONObject().put("excerpt", "我喜欢傍晚去公园散步。")))
        val state = CallUi(active = true, ready = true, phase = CallPhase.SPEAKING, status = "正在说",
            transcript = "我平时喜欢做什么？", answer = "我喜欢傍晚去公园散步。", sources = answer)
        show { VoiceCallContent(state, {}, {}, {}) }
        ui.onNodeWithText(state.answer).assertIsDisplayed()
        ui.onNodeWithTag("voice-text-toggle").performClick()
        ui.onNodeWithText(state.answer).assertDoesNotExist()
        ui.onNodeWithText("显示文字").assertIsDisplayed()
        ui.onNodeWithTag("voice-text-toggle").performClick()
        ui.onNodeWithText(state.answer).assertIsDisplayed(); shot("09-inline-dialogue")
        ui.onNodeWithTag("voice-details").performClick()
        ui.onNodeWithText("本人原话").assertIsDisplayed()
        ui.onAllNodesWithText(state.answer).onLast().assertIsDisplayed(); shot("05-conversation")
        ui.onNodeWithText("查看回答依据").performScrollTo().performClick()
        ui.onAllNodesWithText("我喜欢傍晚去公园散步。").onLast().performScrollTo().assertIsDisplayed(); shot("06-evidence")
        ui.onNodeWithText("收起").performClick()
        ui.onNodeWithText(state.answer).assertIsDisplayed()
        ui.onNodeWithText("结束").assertIsDisplayed()
    }
    @Test fun longDialogueAtLargeFontCanScrollWithoutHidingCallControls() {
        val text = "这是用来检查排版的示例文字。".repeat(20)
        show(fontScale = 1.6f) { VoiceCallContent(CallUi(active = true, ready = true, phase = CallPhase.SPEAKING,
            status = "正在说", transcript = "可以把刚才的内容讲详细一点吗？", answer = text), {}, {}, {}) }
        ui.onNodeWithText("结束").assertIsDisplayed()
        ui.onNodeWithTag("voice-details").performScrollTo().assertIsDisplayed()
        ui.onNodeWithText("结束").assertIsDisplayed(); shot("10-large-text-dialogue")
        ui.onNodeWithTag("voice-text-toggle").performClick()
        ui.onNodeWithText(text).assertDoesNotExist()
        ui.onNodeWithText("暂停").assertIsDisplayed()
    }
    @Test fun largeTextAndFailureKeepExitReachable() {
        show(fontScale = 1.6f) { VoiceCallContent(CallUi(active = false, phase = CallPhase.FAILED, status = "已结束",
            error = "连接中断，请重新进入语音聊聊"), {}, {}, {}) }
        ui.onNodeWithText("返回").assertIsDisplayed()
        ui.onNodeWithTag("voice-status").performScrollTo().assertIsDisplayed(); shot("07-large-text-failure")
    }
    @Test fun textChatKeepsOptionalToolsCollapsed() {
        val audio = AndroidAudioCaptureService(ui.activity)
        val model = NativeWorkbenchModel(ui.activity, audio)
        val state = NativeState(actor = "local-fixture", space = JSONObject().put("role", "owner").put("subject_id", "fixture"),
            narrative = JSONObject().put("style", JSONObject().put("enabled", true)))
        show { Column(Modifier.fillMaxSize().atmosphere(scene = NatureScene.Lake).systemBarsPadding()
            .verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            AskTab(state, model)
        } }
        ui.onNodeWithText("先录下我的回答，再对照").assertDoesNotExist()
        ui.onNodeWithText("分身声音与亲友许可").assertDoesNotExist()
        shot("08-text-chat")
        ui.onNodeWithText("对话工具").performScrollTo().performClick()
        ui.onNodeWithText("允许分身使用已确认的理解与表达").performScrollTo().assertIsDisplayed()
        ui.onNodeWithText("分身声音与亲友许可").performScrollTo().assertIsDisplayed()
        audio.release()
    }
}

/** Runs against the signed APK without a debug-only Compose host Activity. */
class VoiceEngineInstrumentedTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun waitUntil(timeout: Long, condition: () -> Boolean) {
        val deadline = android.os.SystemClock.elapsedRealtime() + timeout
        while (!condition()) {
            check(android.os.SystemClock.elapsedRealtime() < deadline) { "Playback condition timed out" }
            Thread.sleep(10)
        }
    }
    @Test fun engineRejectsOldRoundAndDoesNotReportSpeechForTextAlone() {
        val engine = VoiceCallEngine(context, { true }, { true })
        val type = engine.javaClass
        type.getDeclaredField("sessionId").apply { isAccessible = true }.set(engine, "fixture-session")
        @Suppress("UNCHECKED_CAST") val flow = type.getDeclaredField("mutable").apply { isAccessible = true }.get(engine) as MutableStateFlow<CallUi>
        flow.value = CallUi(active = true, ready = true)
        val event = type.getDeclaredMethod("event", JSONObject::class.java).apply { isAccessible = true }
        fun send(kind: String, turn: Int, extra: JSONObject = JSONObject()) {
            extra.put("type", kind).put("turn_id", turn).put("session_id", "fixture-session")
            event.invoke(engine, extra)
        }
        try {
            send("turn_started", 2, JSONObject().put("question", "新的问题"))
            send("answer_ready", 2, JSONObject().put("answer", JSONObject().put("answer", "新的回答")))
            assertEquals(CallPhase.PREPARING, engine.ui.value.phase)
            send("transcript", 1, JSONObject().put("text", "旧的字幕"))
            send("error", 1, JSONObject().put("message", "旧错误"))
            assertEquals("新的问题", engine.ui.value.transcript)
            assertEquals("新的回答", engine.ui.value.answer)
            assertEquals("", engine.ui.value.error)
            engine.interrupt()
            send("answer_ready", 2, JSONObject().put("answer", JSONObject().put("answer", "已打断的回答")))
            assertEquals("", engine.ui.value.answer)
            send("interrupted", 3)
            send("turn_started", 3, JSONObject().put("question", "再问一句"))
            send("answer_ready", 3, JSONObject().put("answer", JSONObject().put("answer", "文字回答")))
            send("audio_end", 3, JSONObject().put("samples", 0))
            assertEquals(CallPhase.LISTENING, engine.ui.value.phase)
        } finally { engine.close() }
    }
    @Test fun realPlaybackProgressDoesNotResetTheNextQuestion() {
        val engine = VoiceCallEngine(context, { true }, { true })
        val type = engine.javaClass
        fun field(name: String) = type.getDeclaredField(name).apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST") val flow = field("mutable").get(engine) as MutableStateFlow<CallUi>
        flow.value = CallUi(active = true, ready = true, phase = CallPhase.PREPARING, status = "准备播报")
        field("sessionId").set(engine, "fixture-playback")
        field("turn").setLong(engine, 1)
        field("trackTurn").setLong(engine, 1)
        field("receivedSamples").setLong(engine, 24000)
        field("expectedSamples").set(engine, 24000L)
        val track = AudioTrack.Builder().setAudioAttributes(AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(24000).setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
            .setTransferMode(AudioTrack.MODE_STATIC).setBufferSizeInBytes(48000).build()
        field("track").set(engine, track)
        val acknowledge = type.getDeclaredMethod("acknowledge").apply { isAccessible = true }
        try {
            assertEquals(48000, track.write(ByteArray(48000), 0, 48000))
            track.play()
            waitUntil(5000) { acknowledge.invoke(engine); engine.ui.value.phase == CallPhase.SPEAKING }
            waitUntil(5000) { acknowledge.invoke(engine); engine.ui.value.phase == CallPhase.LISTENING }
            assertNull(field("expectedSamples").get(engine))
            flow.value = flow.value.copy(phase = CallPhase.THINKING, status = "正在想", transcript = "下一句")
            repeat(3) { acknowledge.invoke(engine) }
            assertEquals(CallPhase.THINKING, engine.ui.value.phase)
            assertEquals("下一句", engine.ui.value.transcript)
        } finally { engine.close() }
    }
}
