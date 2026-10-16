package me.remember.app

import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.hardware.*
import me.remember.app.integration.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Opt-in real ASR + memory + cumulative worker test. Audio is fictional E01;
 * transport input is a retained synthetic raw file, never a physical recorder. */
class AutomaticCaptureCloudTest {
    @get:Rule val ui=createAndroidComposeRule<MainActivity>()
    @Test fun receivedAudioAutomaticallyReachesDraftThenSaveUpdatesCumulativeAnalysis() {
        val inst=InstrumentationRegistry.getInstrumentation()
        fun shell(command: String)=ParcelFileDescriptor.AutoCloseInputStream(inst.uiAutomation.executeShellCommand(command)).use {it.readBytes()}
        val cfg=JSONObject(String(shell("cat /data/local/tmp/remember-hardware-login.json")))
        val model=ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
        val folder=File(ui.activity.getExternalFilesDir(null),"automatic-cloud-proof").apply {mkdirs()}
        val report=JSONObject().put("physical_device",false).put("audio","fictional E01 synthetic speech")
            .put("version",BuildConfig.VERSION_NAME).put("backend","real deployed API, ASR and model workers")
        fun shot(name: String) {
            ui.waitForIdle()
            // Compose semantics may settle before the platform dialog/window
            // transition reaches the compositor. Capture the presented frame.
            Thread.sleep(500); inst.waitForIdleSync()
            val bitmap=inst.uiAutomation.takeScreenshot()
            File(folder,"$name.png").outputStream().use {bitmap.compress(Bitmap.CompressFormat.PNG,100,it)};bitmap.recycle()
        }
        ui.waitUntil(90000) {!model.ui.value.busy}
        ui.runOnIdle {model.signIn("https://39.108.183.47",cfg.getString("username"),cfg.getString("password"))}
        ui.waitUntil(90000) {model.ui.value.owner && !model.ui.value.busy || model.ui.value.error!=null}
        assertNull(model.ui.value.error)
        try {
            val identity=model.hardwareScope()
            val fileId=(System.currentTimeMillis()/1000).toInt()
            val journal=Work3200ImportJournal(File(ui.activity.filesDir,"work3200-imports"))
            val raw=File(journal.rawDirectory,"auto-cloud-$fileId.raw").apply {writeBytes(shell("cat /data/local/tmp/remember-home-speech.raw"))}
            val entry=journal.recordDownloaded(identity,"synthetic-auto-0162",DeviceRecording(fileId,0,raw.length().toInt(),88340,0),raw)
            val receipt=journal.rawReceipt(entry.importId,identity)
            journal.recordDeviceSignal(identity,"synthetic-auto-0162",fileId,DeviceMarkerPackets.fingerprint(raw.readBytes().copyOfRange(19200,19360)))
            val wav=DeviceOpusDecoder.decode(raw,File(journal.preparedDirectory,"${entry.importId}.wav"))
            journal.prepare(entry.importId,identity,wav,"android-mediacodec-fixed160-v1")
            val candidate=journal.uploadCandidate(entry.importId,identity)
            val points=journal.resolveDevicePackets(entry.importId,identity,candidate.audio.durationMs)
            assertEquals(listOf(RecorderMark(2400,"device")),points)
            journal.saveMarkers(identity,"synthetic-auto-0162",fileId,points)
            ui.runOnIdle {model.acceptRecorderAudio(receipt,candidate)} // no play/upload action
            shot("00-automatic-upload")
            ui.waitUntil(120000) {model.ui.value.local.any {it.key==candidate.idempotencyKey && it.linked}}
            val episode=model.ui.value.local.single {it.key==candidate.idempotencyKey}.episode
            report.put("episode_id",episode).put("automatic_upload",true)
            ui.waitUntil(240000) {episode in model.ui.value.drafts || model.ui.value.stories.any {it.text("episode_id")==episode && it.text("status") in setOf("ready","failed")}}
            val draft=model.ui.value.drafts[episode]
            if(draft!=null) {
                assertTrue(draft.machine.isNotBlank());assertTrue(draft.text.isNotBlank())
                assertEquals(1,draft.highlights!!.getInt("device_marker_count"))
                assertEquals(0,draft.highlights.getInt("phone_marker_count"))
                report.put("device_marker_offset_ms",draft.highlights.getJSONArray("markers").getJSONObject(0).getLong("offset_ms"))
                assertTrue(model.ui.value.stories.single {it.text("episode_id")==episode}.rows("memories").isEmpty())
                ui.runOnIdle {model.focusDraft(episode)}
                ui.onNodeWithTag("capture-draft-text").assertIsDisplayed()
                ui.onNodeWithTag("capture-save-memory").assertIsDisplayed();shot("01-real-cloud-draft")
                ui.onNodeWithText("设备重点 1").performClick()
                ui.onNodeWithText("00:02.400 · 附近文字").assertIsDisplayed();shot("02b-device-marker")
                ui.onNodeWithText("关闭").performClick()
                ui.onNodeWithTag("capture-save-memory").assertIsDisplayed()
                ui.runOnIdle {model.editDraft(episode,draft.text,"这段素材是虚构人物林岚的测试故事，不是真实人物经历。")}
                shot("02-one-save")
                ui.onNodeWithTag("capture-save-memory").performClick()
                ui.waitUntil(10000) { ui.onAllNodesWithText("已保存，正在整理记忆").fetchSemanticsNodes().isNotEmpty() }
                ui.onNodeWithText("已保存，正在整理记忆").assertIsDisplayed();shot("02c-memory-processing")
                ui.waitUntil(90000) {!model.ui.value.busy}
                assertNull(model.ui.value.error)
                report.put("saved_once_from_ui",true)
            }
            ui.waitUntil(240000) {model.ui.value.stories.any {it.text("episode_id")==episode && it.text("status") in setOf("ready","failed")}}
            var story=model.ui.value.stories.single {it.text("episode_id")==episode}
            assertEquals("ready",story.text("status"));assertTrue(story.rows("memories").isNotEmpty())
            ui.waitUntil(240000) {model.ui.value.stories.any {it.text("episode_id")==episode &&
                it.optJSONObject("cumulative_analysis")?.text("status") in setOf("complete","failed","authorization_required")}}
            story=model.ui.value.stories.single {it.text("episode_id")==episode}
            report.put("memories",story.rows("memories").size).put("cumulative_analysis",story.optJSONObject("cumulative_analysis"))
            assertEquals("complete",story.optJSONObject("cumulative_analysis")?.text("status"))
            assertFalse(model.ui.value.drafts.containsKey(episode))
            assertEquals(episode,journal.uploadCandidate(entry.importId,identity).episodeId)
            report.put("ok",true)
            ui.runOnIdle {model.focusDraft(episode)}
            shot("03-real-cloud-complete")
        } finally {File(folder,"result.json").writeText(report.toString(2))}
    }
}
