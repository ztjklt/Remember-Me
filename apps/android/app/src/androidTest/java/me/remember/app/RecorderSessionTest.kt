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
    private var controllerUnderTest: Work3200Controller? = null
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
    @Test fun physicalEventsWaitForLiveDrainAndSaveExactlyOneFile() = runSession(true)
    @Test fun cancelledPendingRealtimeRequestDoesNotBlockOfflineSync() = runSession(false)
    @Test fun maintenanceIsIsolatedAndWifiCancelCannotCancelOtherCommands() {
        lateinit var controller: Work3200Controller
        lateinit var fake: FakeRecorder
        val scope=HardwareScope("https://example.invalid","test-${UUID.randomUUID()}","subject")
        main { controller=Work3200Controller(instrumentation.targetContext,scope,::grant,
            transportFactory={FakeRecorder(it,false).also { fake=it }}); controller.authorize() }
        try {
            await("authorized"){controller.ui.value.authorized}
            main {controller.connect(NearbyRecorder("A","D3200","A","A"))}
            await("connected"){controller.ui.value.connected}
            main {fake.events.deviceLogs(listOf(RecorderLog(10,20)),true)}
            await("logs"){controller.ui.value.maintenance.logs.size==1}
            main {controller.runCommand(RecorderCommand.LOG_DOWNLOAD,10); controller.closeWifi()}
            assertEquals("maintenance",controller.ui.value.busy)
            assertEquals(RecorderCommand.LOG_DOWNLOAD,fake.commands.single())
            main {fake.events.commandResult(RecorderCommand.LOG_DOWNLOAD,true,"test completion")}
            await("completion retained"){controller.ui.value.busy.isEmpty()}
            main {fake.events.linkRecovering()}
            await("wifi handover retains session"){controller.ui.value.reconnecting && controller.ui.value.authorized}
            main {fake.events.connected()}
            await("bluetooth recovered"){controller.ui.value.connected && !controller.ui.value.reconnecting}
            assertEquals(10,controller.ui.value.maintenance.logs.single().id)
            main {controller.disconnect();controller.authorize()}
            await("reauthorized"){controller.ui.value.authorized}
            main {controller.connect(NearbyRecorder("B","D3200","B","B"))}
            await("B connected"){controller.ui.value.connected}
            assertTrue(controller.ui.value.maintenance.logs.isEmpty())
            main {controller.runCommand(RecorderCommand.LOG_DELETE,10)}
            assertTrue(fake.commands.isEmpty())
            main {fake.events.recording(1,0,1700000010)}
            await("recording"){controller.ui.value.recordPhase==DeviceRecordPhase.RECORDING}
            main {controller.runCommand(RecorderCommand.RESET);controller.runCommand(RecorderCommand.PAUSE)}
            assertEquals(listOf(RecorderCommand.PAUSE),fake.commands)
            main {fake.events.recording(2,-1,-1);fake.events.commandResult(RecorderCommand.PAUSE,true,"paused")}
            await("paused"){controller.ui.value.recordPhase==DeviceRecordPhase.PAUSED && controller.ui.value.busy.isEmpty()}
        } finally {main {controller.close()}}
    }
    private fun runSession(realtimeStarted: Boolean) {
        lateinit var controller: Work3200Controller
        lateinit var fake: FakeRecorder
        var prepared: HardwareUploadCandidate? = null
        val scope = HardwareScope("https://example.invalid", "test-${UUID.randomUUID()}", "subject")
        main {
            controller = Work3200Controller(instrumentation.targetContext, scope, ::grant,
                onPrepared = { _, audio -> prepared = audio }, transportFactory = { FakeRecorder(it, realtimeStarted).also { fake = it } })
            controllerUnderTest = controller
            controller.authorize()
        }
        try {
            await("authorized") { controller.ui.value.authorized }
            main { controller.connect(NearbyRecorder("Synthetic recorder", "D3200", "test-mac", "test-uuid")) }
            await("connected") { controller.ui.value.connected }
            main { fake.events.recording(1, -1, 1700000000); fake.events.recordingDuration(1200) }
            await("physical button reflected") { controller.ui.value.recordPhase == DeviceRecordPhase.RECORDING && controller.ui.value.elapsedMs >= 1200 }
            main { controller.addMark(); fake.events.markers(1700000000, intArrayOf(500)) }
            await("both marker sources") { controller.ui.value.recordMarks.size == 2 }
            val markedAudio=instrumentation.context.assets.open("synthetic-device.raw").use {it.readBytes()}.copyOfRange(800,960)
            main {fake.events.audioFragment(1700000000,markedAudio,false,999,true)}
            main { fake.events.recording(2, -1, -1) }
            await("pause with absent file ID") { controller.ui.value.recordPhase == DeviceRecordPhase.PAUSED }
            main { fake.events.recording(1, -1, -1) }
            await("actual SDK resume without ID") { controller.ui.value.recordPhase == DeviceRecordPhase.RECORDING }
            main { controller.runCommand(RecorderCommand.PAUSE) }
            assertEquals("maintenance", controller.ui.value.busy)
            // A physical stop can race the app's pending pause; the real stop wins.
            main { fake.events.recording(0, 2000, -1); fake.events.recording(0, 2000, -1) }
            if (realtimeStarted) {
                Thread.sleep(1800) // Live backlog exceeds the old one-second offline queue delay.
                assertEquals("offline transfer must wait for live drain", 0, fake.transfers)
            }
            main { fake.events.recording(1, 0, 1700000000) }
            await("late start cannot reopen stopped file") { controller.ui.value.recordPhase == DeviceRecordPhase.ENDED }
            if (realtimeStarted) main { fake.events.transfer(1700000000, 3) }
            await("download and decode") { prepared != null }
            assertEquals("WORK_3200", prepared!!.source)
            assertEquals(1, fake.transfers)
            assertEquals(1, controller.ui.value.downloads.size)
            await("device packet mapped to original audio, not guessed from sequence 999") {controller.ui.value.savedMarks.values.singleOrNull()?.contains(RecorderMark(100,"device"))==true}
            assertEquals(3, controller.ui.value.savedMarks.values.single().size)
            main { fake.events.error("file_list", 2) }
            await("recoverable error") { controller.ui.value.message.contains("列表") }
            assertTrue(controller.ui.value.connected)
        } finally { main { controller.close() } }
    }
    private inner class FakeRecorder(val events: HardwareEvents, val realtimeStarted: Boolean) : HardwareTransport {
        var transfers = 0
        val commands=mutableListOf<RecorderCommand>()
        override fun command(command: RecorderCommand,fileId: Int,firmware: RecorderFirmware?) { commands.add(command) }
        override fun initialize(application: Any, credentials: Work3200Credentials) { events.auth(HardwareAuthResult(true, true, true, Long.MAX_VALUE, false, null)) }
        override fun scan() { }
        override fun stopScan() { }
        override fun connect(address: String, id: String) { events.connected() }
        override fun bind() { events.binding(true) }
        override fun realtime(directory: File) { if (realtimeStarted) events.transferIdle(false) }
        override fun listFiles() { events.files(listOf(DeviceRecording(1700000000, 0, 16000, 2000, 0)), true) }
        override fun transfer(recording: DeviceRecording, privateDownloadDirectory: File) {
            transfers++
            val raw = File(privateDownloadDirectory, "synthetic.raw")
            instrumentation.context.assets.open("synthetic-device.raw").use { input -> raw.outputStream().use { input.copyTo(it) } }
            events.progress(recording.fileId, raw.length().toInt(), raw.length().toInt(), 0, false)
            events.transfer(recording.fileId, 4)
            // Late error from a different file must not cancel this transfer.
            events.fileError(recording.fileId - 1, "file_transfer", 1)
            android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
                assertEquals("100% alone must not create a saved recording", 0, controllerUnderTest!!.ui.value.downloads.size)
                assertEquals("download", controllerUnderTest!!.ui.value.busy)
                events.receivedSdkFile(recording.fileId, raw)
            }, 250)
        }
        override fun close() { }
    }
}
