package me.remember.app

import android.Manifest
import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.integration.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.security.MessageDigest

/** Opt-in real native capture and cloud acceptance. No fake ASR or LLM.
 * The desktop supplies virtual-mic TTS then transcribes the actual exported M4A.
 * Import/export service methods are exercised here; SAF picker is a separate check.
 */
class ClientRelayLiveTest {
    @get:Rule val ui = createAndroidComposeRule<MainActivity>()
    private val model get() = ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
    private fun click(label: String) {
        ui.waitUntil(30_000) { ui.onAllNodes(hasText(label) and isEnabled()).fetchSemanticsNodes().isNotEmpty() }
        val node = ui.onAllNodes(hasText(label) and isEnabled()).onFirst()
        if(!node.isDisplayed()) node.performScrollTo()
        node.performClick()
    }
    private fun tab(label: String) = ui.onNodeWithText(label, useUnmergedTree = true).performClick()
    private fun check(label: String) = ui.onAllNodes(isToggleable() and isEnabled() and hasAnySibling(hasText(label, substring = true))).onFirst().performScrollTo().performClick()
    private fun idle() { ui.waitUntil(90_000) { !model.ui.value.busy }; assertNull(model.ui.value.error) }
    private fun shot(name: String) { File(ui.activity.filesDir,"relay-$name.png").outputStream().use { ui.onRoot().captureToImage().asAndroidBitmap().compress(Bitmap.CompressFormat.PNG,100,it) } }
    private fun transfer(capture: LocalCapture, importing: Boolean): String {
        var id: String? = null
        // Same enabled-state rule as the UI button; polling may start during screenshots.
        ui.waitUntil(30_000) { ui.runOnIdle { if(id == null) id = model.beginCaptureTransfer(capture, importing) }; id != null }
        return checkNotNull(id)
    }

    /** Public-IP acceptance only: remove ADB reverse before running. Uses an
     * existing real story; does not pretend to perform new recording or ASR. */
    @Test fun publicIpLoginSourcePlaybackAndTwin() {
        val file = File(ui.activity.filesDir, "public-ip-config.json")
        assumeTrue("Explicit real public-IP test credentials required", file.exists())
        val config = JSONObject(file.readText())
        assertEquals("https://39.108.183.47", BuildConfig.SERVICE_URL)
        ui.waitUntil(45_000) { !model.ui.value.busy }
        if(model.ui.value.actor.isNotBlank()) { tab("我的"); click("退出身份") }
        ui.onNodeWithText("账号").performTextInput(config.getString("username"))
        ui.onNodeWithText("密码（至少10个字符）").performTextInput(config.getString("password"))
        click("登录")
        ui.waitUntil(45_000) { model.ui.value.subject.isNotBlank() && !model.ui.value.busy }
        assertNull(model.ui.value.error)
        val saved = checkNotNull(SavedSession(ui.activity).load())
        assertEquals(BuildConfig.SERVICE_URL, saved.first)
        val episode = config.getString("episode")
        val story = model.ui.value.stories.first { it.optString("episode_id") == episode }
        assertEquals("ready", story.getString("status"))
        assertTrue(story.getJSONArray("memories").length() > 0)
        tab("档案"); shot("public-stories")
        ui.runOnIdle { model.playSource(episode) }
        ui.waitUntil(20_000) { model.ui.value.player.playing }
        ui.runOnIdle { model.seekSource(2_000); model.pauseSource() }
        assertFalse(model.ui.value.player.playing)
        shot("public-player")
        ui.runOnIdle { model.stopSource() }
        val gate = SessionGate()
        val session = gate.connect(saved.first, saved.second)
        val source = BackendClient(gate).audio(session, model.ui.value.subject, episode)
        val hash = MessageDigest.getInstance("SHA-256").digest(source).joinToString("") { "%02x".format(it) }
        assertEquals(config.getString("audio_sha256"), hash)
        tab("对话")
        ui.onNodeWithText("想了解什么？").performTextInput(config.getString("question"))
        check("同意本次将问题和有权访问"); click("提问"); idle()
        val answer = checkNotNull(model.ui.value.answer)
        shot("public-twin")
        tab("档案"); click("人物")
        ui.onNodeWithText("在意与选择").performScrollTo().assertExists()
        shot("public-portrait")
        File(ui.activity.filesDir,"public-ip-result.json").writeText(JSONObject()
            .put("server",saved.first).put("episode",episode).put("audio_sha256",hash)
            .put("story",story).put("answer",answer).put("portrait",model.ui.value.portrait)
            .put("source_playback",true).put("new_recording_tested",false)
            .put("new_asr_tested",false).put("real_handset",false).toString(2))
        tab("我的"); click("退出身份")
        assertNull(SavedSession(ui.activity).load())
        assertTrue(model.ui.value.stories.isEmpty())
    }

    @Test fun systemPickersOpenAndCancelWithoutLosingOriginals() {
        val configFile=File(ui.activity.filesDir,"client-relay-config.json")
        assumeTrue(configFile.exists())
        val config=JSONObject(configFile.readText())
        ui.waitUntil(45_000) { !model.ui.value.busy }
        if(model.ui.value.actor.isBlank()) {
            ui.onNodeWithText("账号").performTextInput(config.getString("username"))
            ui.onNodeWithText("密码（至少10个字符）").performTextInput(config.getString("password"))
            click("登录");idle()
        }
        ui.waitUntil(45_000) { model.ui.value.subject.isNotBlank() && !model.ui.value.busy && model.ui.value.local.isNotEmpty() }
        val files=model.ui.value.local.associate { it.key to File(it.recording.audioPath).length() }
        val automation=InstrumentationRegistry.getInstrumentation().uiAutomation
        for(label in listOf("导出这段原音","取回机器转写")) {
            click(label)
            ui.waitUntil(15_000) { automation.rootInActiveWindow?.packageName?.toString()?.contains("documentsui") == true }
            automation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
            ui.waitUntil(15_000) { automation.rootInActiveWindow?.packageName?.toString() == ui.activity.packageName }
            idle()
        }
        assertEquals(files,model.ui.value.local.associate { it.key to File(it.recording.audioPath).length() })
        tab("我的");click("退出身份")
        File(ui.activity.filesDir,"relay-pickers.json").writeText("{\"open_cancel\":true,\"originals_preserved\":true,\"selected_file_callback_tested\":false}")
    }

    @Test fun nativeCaptureClientDraftEcsMemoryAndTwin() {
        val configFile = File(ui.activity.filesDir,"client-relay-config.json")
        assumeTrue("Explicit private test configuration and desktop relay required", configFile.exists())
        val config = JSONObject(configFile.readText())
        InstrumentationRegistry.getInstrumentation().uiAutomation.grantRuntimePermission(ui.activity.packageName, Manifest.permission.RECORD_AUDIO)
        ui.waitUntil(45_000) { !model.ui.value.busy }
        if(model.ui.value.actor.isNotBlank()) { tab("我的"); click("退出身份") }
        ui.onNodeWithText("账号").performTextInput(config.getString("username"))
        ui.onNodeWithText("密码（至少10个字符）").performTextInput(config.getString("password"))
        click("登录")
        ui.waitUntil(45_000) { model.ui.value.subject.isNotBlank() && !model.ui.value.busy }
        assertEquals("client",model.ui.value.asrCapabilities?.optString("stt"))
        val reusedHash = config.optString("existing_recording_sha256")
        val original: LocalCapture
        if(reusedHash.isBlank()) {
        check("我同意本次麦克风录音"); click("开始录音")
        ui.waitUntil(15_000) { model.ui.value.recording }
        if(!config.optBoolean("skip_pause_resume")) { click("暂停录音"); click("继续录音") }
        File(ui.activity.filesDir,"relay-mic-start").writeText("fictional virtual mic requested")
        ui.waitUntil(80_000) { File(ui.activity.filesDir,"relay-mic-done").exists() }
        click("停止并保留原音"); idle()
        original = model.ui.value.local.first()
        } else {
            // Resume the exact previously captured native original, never an imported WAV.
            original = model.ui.value.local.first { capture ->
                MessageDigest.getInstance("SHA-256").digest(File(capture.recording.audioPath).readBytes()).joinToString("") { "%02x".format(it) } == reusedHash
            }
        }
        fun currentCapture() = model.ui.value.local.first { it.key == original.key }
        if(reusedHash.isBlank()) assertNull(original.transcript)
        else original.transcript?.let { assertEquals(reusedHash,it.audioSha256) }
        ui.runOnIdle { model.playLocal(original) }
        ui.waitUntil(15_000) { model.audio.playback.value.playing }
        click("停止本机播放")
        shot("original")
        val exportId = transfer(original, importing = false)
        ui.runOnIdle { model.exportOriginal(exportId) { File(ui.activity.filesDir,"relay-original.m4a").outputStream() } }
        idle()
        if(config.optBoolean("capture_only")) {
            File(ui.activity.filesDir,"relay-capture-only").writeText("native recording exported; no ASR or Agent called")
            return
        }
        File(ui.activity.filesDir,"relay-asr-start").writeText("transcribe exported real native recording")
        val machineFile = File(ui.activity.filesDir,"relay-machine.json")
        ui.waitUntil(150_000) { machineFile.exists() || File(ui.activity.filesDir,"relay-error").exists() }
        assertFalse("Desktop relay refused invalid audio/ASR",File(ui.activity.filesDir,"relay-error").exists())
        val importId = transfer(original, importing = true)
        ui.runOnIdle { model.importTranscript(importId) { machineFile.inputStream() } }
        idle()
        val machine = currentCapture().transcript!!
        assertEquals(JSONObject(machineFile.readText()).getJSONObject("client_transcript").getString("text"), machine.text)
        ui.activityRule.scenario.recreate()
        ui.waitUntil(45_000) { !model.ui.value.busy && model.ui.value.local.isNotEmpty() }
        assertEquals(machine.text, currentCapture().transcript?.text)
        check("同意将本段完整原音及机器稿保存到服务器")
        click("上传并等待核对"); idle()
        val capture = currentCapture()
        assertTrue(capture.uploadAttempted && capture.linked && capture.episode.isNotBlank())
        val episode = capture.episode
        assertTrue(model.ui.value.stories.first { it.optString("episode_id") == episode }.optBoolean("waiting_for_review"))
        shot("draft")
        tab("档案"); click("核对转写"); idle()
        assertTrue(model.ui.value.reviewText.isNotBlank())
        // The server may normalize traditional characters in the review draft.
        // The raw draft remains unchanged in the capture ledger; never overwrite it.
        assertEquals(machine.text,currentCapture().transcript?.text)
        val reviewBeforeConfirmation = model.ui.value.reviewText
        // Explicitly authorized technical confirmation, not claimed human listening.
        ui.runOnIdle { model.editSupplement(config.getString("supplement")) }
        check("我确认文字与补充说明"); click("确认文字并整理"); idle()
        ui.waitUntil(150_000) { model.ui.value.stories.any { it.optString("episode_id") == episode && it.optString("status") in listOf("ready","failed") } }
        val story = model.ui.value.stories.first { it.optString("episode_id") == episode }
        assertEquals(story.optString("error_message"),"ready",story.optString("status"))
        assertEquals(reviewBeforeConfirmation,story.optString("transcript"))
        assertEquals(machine.text,story.optString("machine_transcript"))
        assertTrue(story.getJSONArray("memories").length()>0)
        shot("memory")
        ui.runOnIdle { model.playSource(episode) }
        ui.waitUntil(20_000) { model.ui.value.player.playing }
        ui.runOnIdle { model.seekSource(2_000); model.pauseSource() }
        assertFalse(model.ui.value.player.playing)
        ui.runOnIdle { model.stopSource() }
        tab("对话")
        ui.onNodeWithText("想了解什么？").performTextInput(config.getString("question"))
        check("同意本次将问题和有权访问"); click("提问"); idle()
        val answer = checkNotNull(model.ui.value.answer)
        shot("twin")
        File(ui.activity.filesDir,"relay-result.json").writeText(JSONObject().put("episode",episode).put("story",story).put("answer",answer)
            .put("machine_text_preserved",true).put("draft_survives_activity_recreation",true).put("source_playback",true)
            .put("native_source","ANDROID_MIC with fictional virtual-mic injection").put("human_listening",false).put("saf_picker_tested",false).toString(2))
        tab("档案"); click("人物")
        ui.onNodeWithText("在意与选择").performScrollTo().assertExists()
        shot("portrait")
        tab("我的"); click("退出身份")
        ui.waitUntil(15_000) { model.ui.value.actor.isBlank() }
        assertTrue(model.ui.value.stories.isEmpty())
        assertNull(SavedSession(ui.activity).load())
        File(ui.activity.filesDir,"relay-complete").writeText("native/ECS flow completed; semantic review separate")
    }
}
