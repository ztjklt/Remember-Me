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

/** Opt-in live backend test. Fictional library speech replaces only device input;
 * no physical recorder, human voice or real device-audio quality claim. */
class RecorderHomeUploadLiveTest {
    @get:Rule val ui = createAndroidComposeRule<MainActivity>()
    @Test fun hardwareFileStaysPlayableAndReachesReviewFromHome() {
        val inst = InstrumentationRegistry.getInstrumentation()
        fun shell(command: String) = ParcelFileDescriptor.AutoCloseInputStream(inst.uiAutomation.executeShellCommand(command)).use { it.readBytes() }
        val cfg = JSONObject(String(shell("cat /data/local/tmp/remember-hardware-login.json")))
        val model = ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
        val folder = File(ui.activity.getExternalFilesDir(null), "recorder-home-proof").apply { mkdirs() }
        val report = JSONObject().put("physical_device", false).put("synthetic_fixture", "memory-garden/E01")
        fun idle() { ui.waitUntil(90000) { !model.ui.value.busy }; assertNull(model.ui.value.error) }
        fun act(block: () -> Unit) { idle(); ui.runOnIdle(block); idle() }
        fun shot(name: String) {
            ui.waitForIdle(); Thread.sleep(400)
            val bitmap = inst.uiAutomation.takeScreenshot()
            File(folder, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle()
        }
        try {
            act { model.signIn("https://39.108.183.47", cfg.getString("username"), cfg.getString("password")) }
            ui.waitUntil(90000) { model.ui.value.owner && !model.ui.value.busy || model.ui.value.error != null }; idle()
            assertTrue(model.ui.value.owner)
            val identity = model.hardwareScope()
            val journal = Work3200ImportJournal(File(ui.activity.filesDir, "work3200-imports"))
            val raw = File(journal.rawDirectory, "fictional-library-home.raw").apply { writeBytes(shell("cat /data/local/tmp/remember-home-speech.raw")) }
            val fileId = 1792110000 // stable fixture identity so reruns cannot duplicate cloud memories
            val entry = journal.recordDownloaded(identity, "synthetic-library-home", DeviceRecording(fileId, 0, raw.length().toInt(), 88340, 0), raw)
            journal.saveMarkers(identity, "synthetic-library-home", fileId, listOf(RecorderMark(1200, "phone"), RecorderMark(2400, "device")))
            val receipt = journal.rawReceipt(entry.importId, identity)
            val decoded = DeviceOpusDecoder.decode(raw, File(journal.preparedDirectory, "${entry.importId}.wav"))
            journal.prepare(entry.importId, identity, decoded, "android-mediacodec-fixed160-v1")
            val candidate = journal.uploadCandidate(entry.importId, identity)
            act { model.acceptRecorderAudio(receipt, candidate); model.acceptRecorderAudio(receipt, candidate) }
            assertEquals(1, model.ui.value.local.count { it.key == candidate.idempotencyKey })
            // New session restores the hardware source, original key and prepared WAV.
            act { model.logout() }
            act { model.signIn("https://39.108.183.47", cfg.getString("username"), cfg.getString("password")) }
            ui.waitUntil(90000) { model.ui.value.owner && !model.ui.value.busy || model.ui.value.error != null }; idle()
            val capture = model.ui.value.local.single { it.key == candidate.idempotencyKey }
            assertEquals("WORK_3200", capture.source); assertTrue(File(capture.recording.audioPath).isFile)
            ui.onNodeWithText("录音豆录音").assertExists()
            shot("01-home-saved")
            if (capture.episode.isBlank()) act { model.upload(capture, true) }
            val episode = model.ui.value.local.single { it.key == capture.key }.episode
            assertTrue(episode.isNotBlank())
            assertEquals(episode, journal.uploadCandidate(entry.importId, identity).episodeId)
            report.put("episode_id", episode).put("duration_ms", candidate.audio.durationMs).put("markers", 2)
            ui.waitUntil(240000) { model.ui.value.stories.any { it.text("episode_id") == episode && (it.optBoolean("waiting_for_review") || it.text("status") in listOf("ready", "failed")) } }
            var story = model.ui.value.stories.single { it.text("episode_id") == episode }
            assertNotEquals("failed", story.text("status"))
            if (story.optBoolean("waiting_for_review")) {
                assertTrue(story.rows("memories").isEmpty())
                report.put("no_memories_before_confirmation", true)
                val node = ui.onAllNodes(hasText("核对本段文字") and hasClickAction()).onFirst()
                node.performScrollTo().performClick(); idle()
                assertEquals(episode, model.ui.value.reviewEpisode)
                assertTrue(model.ui.value.reviewMachineText.isNotBlank())
                shot("02-home-review")
                // Reviewed against the test fixture script, explicitly marked fictional.
                val verified = "这是一段虚构测试素材：林岚在社区图书馆工作。二〇一六年秋天的雨夜，她把备用伞借给忘带伞的老人，晚回家约半小时。家人小雨盖好饭菜等她。第二周老人还伞，留下感谢便条。"
                act { model.confirmReview(verified, true) }
                ui.waitUntil(240000) { model.ui.value.stories.any { it.text("episode_id") == episode && it.text("status") in listOf("ready", "failed") } }
                story = model.ui.value.stories.single { it.text("episode_id") == episode }
            }
            assertEquals("ready", story.text("status")); assertTrue(story.rows("memories").isNotEmpty())
            ui.onAllNodes(hasText("查看本段文字与全部记忆") and hasClickAction()).onFirst().performScrollTo().performClick()
            ui.onNodeWithText("已核对的文字").assertExists()
            ui.onNodeWithText(story.text("transcript")).assertExists()
            assertNull(model.ui.value.reviewEpisode) // submitted text must not reopen a write-once review
            val replay = journal.uploadCandidate(entry.importId, identity)
            assertTrue(replay.file.isFile); assertEquals(candidate.idempotencyKey, replay.idempotencyKey)
            ui.runOnIdle { model.recorder().play(receipt, 2400) }
            ui.waitUntil(30000) { model.recorder().ui.value.playing }
            ui.runOnIdle { model.recorder().stopPlayback() }
            report.put("ok", true).put("status", story.text("status")).put("memories", story.rows("memories").size)
            shot("03-home-organized")
        } finally { File(folder, "result.json").writeText(report.toString(2)) }
    }
}
