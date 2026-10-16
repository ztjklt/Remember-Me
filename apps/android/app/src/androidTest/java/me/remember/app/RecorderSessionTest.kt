package me.remember.app

import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.hardware.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.util.UUID

/** Synthetic SDK boundary only: exercises real controller, journal and Android Opus decoder. */
class RecorderSessionTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private fun main(block: () -> Unit) = instrumentation.runOnMainSync(block)
    private fun await(message: String, condition: () -> Boolean) {
        val end = System.currentTimeMillis() + 15000
        while (System.currentTimeMillis() < end && !condition()) Thread.sleep(30)
        assertTrue(message, condition())
    }
    private fun grant(scope: HardwareScope, device: String): JSONObject {
        val end = System.currentTimeMillis() / 1000 + 3600
        return JSONObject().put("version", 1).put("user_id", scope.actorId).put("device_id", device)
            .put("token", "synthetic-only").put("license_signature", "synthetic-only").put("environment", "DEVELOPMENT")
            .put("token_expire_time", end).put("license_json", JSONObject().put("user_id", scope.actorId)
                .put("device_id", device).put("license_expire_time", end).toString())
    }
    @Test fun physicalEventsSaveExactlyOneFileAndKeepConnectionAfterFileErrors() {
        lateinit var controller: Work3200Controller
        lateinit var fake: FakeRecorder
        var prepared: HardwareUploadCandidate? = null
        val scope = HardwareScope("https://example.invalid", "test-${UUID.randomUUID()}", "subject")
        main {
            controller = Work3200Controller(instrumentation.targetContext, scope, ::grant,
                onPrepared = { _, audio -> prepared = audio }, transportFactory = { FakeRecorder(it).also { fake = it } })
            controller.authorize()
        }
        try {
            await("authorized") { controller.ui.value.authorized }
            main { controller.connect(NearbyRecorder("Synthetic recorder", "D3200", "test-mac", "test-uuid")) }
            await("connected") { controller.ui.value.connected }
            main { fake.events.recording(1, 0, 1700000000); fake.events.recordingDuration(1200) }
            await("physical button reflected") { controller.ui.value.recordPhase == DeviceRecordPhase.RECORDING && controller.ui.value.elapsedMs >= 1200 }
            main { controller.addMark(); fake.events.markers(1700000000, intArrayOf(500)) }
            await("both marker sources") { controller.ui.value.recordMarks.size == 2 }
            main { fake.events.recording(0, 2000, 1700000000); fake.events.recording(0, 2000, 1700000000) }
            await("download and decode") { prepared != null }
            assertEquals("WORK_3200", prepared!!.source)
            assertEquals(1, fake.transfers)
            assertEquals(1, controller.ui.value.downloads.size)
            assertEquals(2, controller.ui.value.savedMarks.values.single().size)
            main { fake.events.error("file_list", 2) }
            await("recoverable error") { controller.ui.value.message.contains("列表") }
            assertTrue(controller.ui.value.connected)
        } finally { main { controller.close() } }
    }
    private inner class FakeRecorder(val events: HardwareEvents) : HardwareTransport {
        var transfers = 0
        override fun initialize(application: Any, credentials: Work3200Credentials) { events.auth(HardwareAuthResult(true, true, true, Long.MAX_VALUE, false, null)) }
        override fun scan() { }
        override fun stopScan() { }
        override fun connect(address: String, id: String) { events.connected() }
        override fun bind() { events.binding(true) }
        override fun listFiles() { events.files(listOf(DeviceRecording(1700000000, 0, 16000, 2000, 0)), true) }
        override fun transfer(recording: DeviceRecording, privateDownloadDirectory: File) {
            transfers++
            val raw = File(privateDownloadDirectory, "synthetic.raw")
            instrumentation.context.assets.open("synthetic-device.raw").use { input -> raw.outputStream().use { input.copyTo(it) } }
            events.progress(recording.fileId, raw.length().toInt(), raw.length().toInt(), 0, false)
            events.receivedSdkFile(recording.fileId, raw)
        }
        override fun close() { }
    }
}
