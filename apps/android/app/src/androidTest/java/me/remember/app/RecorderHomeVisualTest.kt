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

/** Presentation evidence from real production UI with simulated SDK events.
 * Never describe these screenshots as a physical-device connection. */
class RecorderHomeVisualTest {
    @get:Rule val ui = createAndroidComposeRule<MainActivity>()
    @Test fun captureHomeRecordingAndTransferScreens() {
        val inst = InstrumentationRegistry.getInstrumentation()
        fun shell(command: String) = ParcelFileDescriptor.AutoCloseInputStream(inst.uiAutomation.executeShellCommand(command)).use { it.readBytes() }
        val cfg = JSONObject(String(shell("cat /data/local/tmp/remember-hardware-login.json")))
        val model = ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
        val folder = File(ui.activity.getExternalFilesDir(null), "recorder-home-visual").apply { mkdirs() }
        lateinit var controller: Work3200Controller
        lateinit var events: HardwareEvents
        lateinit var received: File
        val fileId = (System.currentTimeMillis() / 1000).toInt()
        val bytes = shell("cat /data/local/tmp/remember-home-speech.raw")
        fun idle() { ui.waitUntil(90000) { !model.ui.value.busy }; assertNull(model.ui.value.error) }
        fun click(text: String) {
            val node = ui.onAllNodes(hasText(text) and hasClickAction()).onFirst()
            if (!node.isDisplayed()) node.performScrollTo()
            node.performClick(); ui.waitForIdle()
        }
        fun shot(name: String) {
            ui.waitForIdle(); Thread.sleep(400)
            val bitmap = inst.uiAutomation.takeScreenshot()
            File(folder, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle()
        }
        idle()
        ui.runOnIdle { model.signIn("https://39.108.183.47", cfg.getString("username"), cfg.getString("password")) }
        ui.waitUntil(90000) { model.ui.value.owner && !model.ui.value.busy || model.ui.value.error != null }; idle()
        try {
            click("我的")
            ui.runOnIdle {
                model.recorder().close()
                controller = Work3200Controller(ui.activity, model.hardwareScope(), model::hardwareGrant,
                    // Visual-only run: do not send another synthetic recording
                    // to cloud; automatic submission has separate acceptance.
                    onPrepared = { _, _ -> }, transportFactory = { sink ->
                        events = sink
                        object : HardwareTransport {
                            override fun initialize(application: Any, credentials: Work3200Credentials) { sink.auth(HardwareAuthResult(true, true, true, Long.MAX_VALUE, false, null)) }
                            override fun scan() { }; override fun stopScan() { }; override fun bind() { sink.binding(true) }
                            override fun connect(address: String, id: String) { sink.connected(); sink.info(9, "04.92", 61074560, 61075712) }
                            override fun listFiles() { sink.files(listOf(DeviceRecording(fileId, 0, bytes.size, 88340, 0)), true) }
                            override fun transfer(recording: DeviceRecording, privateDownloadDirectory: File) {
                                received = File(privateDownloadDirectory, "synthetic-library.raw").apply { writeBytes(bytes) }
                                sink.progress(fileId, bytes.size * 40 / 100, bytes.size, 0, false)
                            }
                            override fun close() { }
                        }
                    })
                // Test-only substitution at SDK boundary; production binary has no demo switch.
                NativeWorkbenchModel::class.java.getDeclaredField("deviceController").apply { isAccessible = true }.set(model, controller)
                model.selectCaptureSource("recorder")
                controller.authorize()
            }
            ui.waitUntil(20000) { controller.ui.value.authorized }
            click("今天")
            // A restored capture shows the expanded card ("设备"); a settled
            // home shows the compact disconnected row ("连接"). Both open the
            // same device panel. Do not couple pairing coverage to cloud history.
            val entry = ui.onAllNodes(hasClickAction() and (hasText("连接") or hasText("设备"))).onFirst()
            if (!entry.isDisplayed()) entry.performScrollTo()
            entry.performClick(); ui.waitForIdle()
            ui.runOnIdle { controller.scan() }
            ui.onNodeWithText("正在搜索设备").assertIsDisplayed(); shot("00a-searching")
            ui.runOnIdle {
                events.found("D3200", "soundcore Work", "02:00:00:00:00:01", "visual-uuid-1")
                events.found("D3200", "soundcore Work", "02:00:00:00:00:02", "visual-uuid-2")
                events.bindingAdvertisement("02:00:00:00:00:01", "visual-uuid-1", true)
                events.bindingAdvertisement("02:00:00:00:00:02", "visual-uuid-2", true)
            }
            ui.onNodeWithText("选择录音豆").assertIsDisplayed(); shot("00b-device-picker")
            ui.onNodeWithText("标识 · 00:01").performClick()
            ui.waitUntil(10000) { controller.ui.value.connected && controller.ui.value.busy.isEmpty() }
            click("关闭")
            shot("00-home-before-recording")
            val motion = InstrumentationRegistry.getArguments().getString("motionCapture") == "true"
            // Infinite animations started while the test clock auto-advances are
            // suppressed by Compose's test policy. Set the policy before opening.
            if(motion) ui.mainClock.autoAdvance = false
            click("设备")
            if(motion) { ui.mainClock.advanceTimeBy(1000); ui.waitForIdle() }
            ui.onNodeWithTag("recorder-product-hero").assertIsDisplayed()
            ui.onNodeWithText("设备设置").assertIsDisplayed()
            shot("00-connected-product")
            if (motion) {
                File(folder,"motion-final-ready-0163.txt").writeText("Product animation on emulator; simulated SDK connection")
                // Drive the Compose test clock at wall-clock speed for a direct
                // screen recording of the production GPU transform.
                repeat(840) { ui.mainClock.advanceTimeBy(16); Thread.sleep(16) }
                ui.mainClock.autoAdvance = true
            }
            click("关闭")
            ui.runOnIdle { events.recording(1, -1, fileId); events.recordingDuration(18000) }
            ui.waitUntil(10000) { controller.ui.value.recordPhase == DeviceRecordPhase.RECORDING }
            ui.onAllNodes(hasText("标记重点", substring=true) and hasClickAction()).assertCountEquals(0)
            ui.onNodeWithText("双敲机身标重点").assertIsDisplayed(); shot("00-recording-before-marker")
            ui.runOnIdle { events.realtimeMarker(fileId, 200); events.markers(fileId, intArrayOf(1200)) }
            ui.onNodeWithText("正在录音").assertIsDisplayed(); shot("01-recording-simulated-events")
            click("我的"); click("今天")
            ui.runOnIdle { assertSame(controller, model.recorder()); assertTrue(controller.ui.value.connected) }
            click("设备")
            ui.onNodeWithText("关闭").assertExists()
            ui.onNodeWithTag("recorder-status-row").performScrollTo().assertIsDisplayed()
            ui.onNodeWithText("数据来自录音豆",substring=true).assertDoesNotExist()
            ui.onNodeWithText("连接期间持续计时",substring=true).assertDoesNotExist()
            ui.onNodeWithText("传输：",substring=true).assertDoesNotExist()
            ui.onNodeWithText("连接录音豆").assertDoesNotExist()
            ui.onNodeWithText("导出连接与下载记录").assertDoesNotExist()
            shot("01b-device-status-simulated-events")
            ui.runOnIdle { events.recording(0, 88340, -1) }
            ui.waitUntil(15000) { controller.ui.value.percent == 40 && controller.ui.value.busy == "download" }
            ui.onNodeWithText("关闭").assertDoesNotExist()
            ui.onNodeWithText("收到录音，正在同步").assertIsDisplayed(); shot("02-download-simulated-events")
            ui.runOnIdle { events.progress(fileId, bytes.size * 70 / 100, bytes.size, 0, false) }
            Thread.sleep(1200)
            shot("02b-download-70-percent")
            ui.runOnIdle { events.progress(fileId, bytes.size, bytes.size, 1, false); events.receivedSdkFile(fileId, received) }
            try {
                // Wait on background MediaCodec work in wall-clock time. Advancing
                // the Compose test clock on every poll needlessly drives each
                // finite progress animation while native decoding is running.
                val deadline = System.currentTimeMillis() + 120000
                while (controller.ui.value.busy.isNotEmpty() && System.currentTimeMillis() < deadline) Thread.sleep(100)
                assertTrue("Decoded recording must be saved", controller.ui.value.busy.isEmpty() && controller.ui.value.downloads.any { it.fileId==fileId })
            } catch(e: Throwable) {
                shot("failure-download-state")
                throw AssertionError("Download did not settle: busy=${controller.ui.value.busy}; ${controller.ui.value.message}", e)
            }
            shot("03-saved-synthetic-audio")
            File(folder, "evidence.json").writeText(JSONObject().put("version", BuildConfig.VERSION_NAME).put("physical_device", false)
                .put("sdk_events", "simulated").put("ui", "production NativeWorkbenchScreen").put("decoder", "real Android MediaCodec")
                .put("tab_switch_retains_session", true).toString(2))
        } finally { ui.runOnIdle { controller.close(); model.logout() } }
    }
}
