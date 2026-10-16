package me.remember.app

import android.Manifest
import android.app.ActivityManager
import android.content.Context
import android.net.Uri
import android.os.Build
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import me.remember.app.hardware.*
import me.remember.app.integration.Work3200Panel
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.UUID

class RecorderForegroundTest {
    @get:Rule val ui = createAndroidComposeRule<MainActivity>()
    @Suppress("DEPRECATION")
    @Test fun cancellingBeforeServiceCreationDoesNotKillTheApp() {
        val context=ui.activity
        val automation=androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().uiAutomation
        if(Build.VERSION.SDK_INT>=31) listOf(Manifest.permission.BLUETOOTH_SCAN,Manifest.permission.BLUETOOTH_CONNECT).forEach {
            automation.grantRuntimePermission(context.packageName,it)
        }
        val manager=context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        repeat(5) {
            ui.runOnIdle {
                val controller=Work3200Controller(context,HardwareScope("https://example.invalid","cancel-${UUID.randomUUID()}","subject"),
                    getGrant={_,_->error("unused")})
                controller.keepConnectedInBackground()
                controller.close() // Same main-loop turn, before Service.onCreate.
            }
            ui.waitForIdle()
            Thread.sleep(300) // Allow Android to deliver asynchronous service start/cancel.
            ui.waitUntil(10000) { manager.getRunningServices(100).none {it.service.className==RecorderConnectionService::class.java.name} }
        }
        ui.runOnIdle { assertFalse(context.isFinishing);assertFalse(context.isDestroyed) }
    }
    @Suppress("DEPRECATION")
    @Test fun importedGrantRestoresServiceAndPanelDisposalKeepsConnection() {
        val context = ui.activity
        val automation = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().uiAutomation
        if (Build.VERSION.SDK_INT >= 31) listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT).forEach {
            automation.grantRuntimePermission(context.packageName, it)
        }
        val manager = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        fun foreground() = manager.getRunningServices(100).any { it.service.className == RecorderConnectionService::class.java.name && it.foreground }
        lateinit var controller: Work3200Controller
        lateinit var events: HardwareEvents
        var closed = false
        val scope = HardwareScope("https://example.invalid", "service-${UUID.randomUUID()}", "subject")
        val visible = mutableStateOf(true)
        ui.runOnIdle {
            controller = Work3200Controller(context, scope, getGrant = { _, _ -> error("synthetic auth unavailable") }, transportFactory = { sink ->
                events = sink
                object : HardwareTransport {
                    override fun initialize(application: Any, credentials: Work3200Credentials) { sink.auth(HardwareAuthResult(true, true, true, Long.MAX_VALUE, false, null)) }
                    override fun scan() { }; override fun stopScan() { }; override fun bind() { }; override fun listFiles() { }
                    override fun connect(address: String, id: String) { sink.connected() }
                    override fun transfer(recording: DeviceRecording, privateDownloadDirectory: File) { }
                    override fun close() { closed = true }
                }
            })
            context.setContent { MaterialTheme { Column(Modifier.verticalScroll(rememberScrollState())) {
                if (visible.value) Work3200Panel(controller, compact = true) else Text("另一页面")
            } } }
            controller.keepConnectedInBackground(); controller.authorize()
        }
        try {
            ui.waitUntil(15000) { controller.ui.value.needsGrant && !foreground() }
            val device = JSONObject(controller.authorizationRequest()).getString("device_id")
            val end = System.currentTimeMillis() / 1000 + 3600
            val grant = JSONObject().put("version", 1).put("user_id", scope.actorId).put("device_id", device)
                .put("token", "synthetic").put("license_signature", "synthetic").put("environment", "DEVELOPMENT")
                .put("token_expire_time", end).put("license_json", JSONObject().put("user_id", scope.actorId).put("device_id", device).put("license_expire_time", end).toString())
            val file = File(context.cacheDir, "synthetic-service-grant.json").apply { writeText(grant.toString()) }
            ui.runOnIdle { controller.importGrant(Uri.fromFile(file)) }
            ui.waitUntil(15000) { controller.ui.value.authorized && foreground() }
            ui.runOnIdle { controller.connect(NearbyRecorder("Synthetic", "D3200", "synthetic", "synthetic")) }
            ui.waitUntil(10000) { controller.ui.value.connected }
            ui.runOnIdle { events.recording(1, 2000, 1700000000) }
            ui.waitUntil(10000) { controller.ui.value.recordPhase == DeviceRecordPhase.RECORDING }
            ui.onNodeWithText("正在录音").assertExists()
            ui.runOnIdle { visible.value = false }
            ui.onNodeWithText("另一页面").assertExists()
            assertFalse("disposing the device panel must not close SDK", closed)
            assertTrue(foreground()); assertTrue(controller.ui.value.connected)
            ui.runOnIdle { visible.value = true }
            ui.onNodeWithText("正在录音").assertExists()
        } finally { ui.runOnIdle { controller.close() }; ui.waitUntil(10000) { !foreground() } }
    }
}
