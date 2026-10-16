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
            ui.runOnIdle { controller.connect(NearbyRecorder("soundcore Work · 演示事件", "D3200", "visual-mac", "visual-uuid", true)) }
            ui.waitUntil(10000) { controller.ui.value.connected && controller.ui.value.busy.isEmpty() }
            click("今天")
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
            ui.runOnIdle { events.progress(fileId, bytes.size, bytes.size, 1, false); events.receivedSdkFile(fileId, received) }
            ui.waitUntil(30000) { controller.ui.value.busy.isEmpty() && controller.ui.value.downloads.any { it.fileId==fileId } }
            shot("03-saved-synthetic-audio")
            File(folder, "evidence.json").writeText(JSONObject().put("version", BuildConfig.VERSION_NAME).put("physical_device", false)
                .put("sdk_events", "simulated").put("ui", "production NativeWorkbenchScreen").put("decoder", "real Android MediaCodec")
                .put("tab_switch_retains_session", true).toString(2))
        } finally { ui.runOnIdle { controller.close(); model.logout() } }
    }
}
