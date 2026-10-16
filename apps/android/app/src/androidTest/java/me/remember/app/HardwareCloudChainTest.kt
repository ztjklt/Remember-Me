package me.remember.app

import android.os.ParcelFileDescriptor
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.hardware.Work3200Controller
import me.remember.app.integration.NativeWorkbenchModel
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

/** App session -> deployed broker -> real SDK, then close and reinitialize. No Bluetooth fixture. */
class HardwareCloudChainTest {
    @get:Rule val ui = createAndroidComposeRule<MainActivity>()
    @Test fun authenticatedAppCanAuthorizeAgainAfterClosingSdk() {
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        val cfg = JSONObject(ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand("cat /data/local/tmp/remember-hardware-login.json")).bufferedReader().use { it.readText() })
        val model = ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
        ui.runOnIdle { model.signIn("https://39.108.183.47", cfg.getString("username"), cfg.getString("password")) }
        ui.waitUntil(60_000) { model.ui.value.actor.isNotBlank() && !model.ui.value.busy || model.ui.value.error != null }
        assertNull(model.ui.value.error); assertTrue(model.ui.value.owner)
        var onlineRequests = 0
        repeat(2) {
            lateinit var controller: Work3200Controller
            ui.runOnIdle {
                controller = Work3200Controller(ui.activity, model.hardwareScope(), getGrant = { scope, device ->
                    model.hardwareGrant(scope, device).also { onlineRequests++ }
                })
                controller.authorize()
            }
            try {
                ui.waitUntil(60_000) { controller.ui.value.authorized || controller.ui.value.busy.isEmpty() }
                assertTrue(controller.ui.value.message, controller.ui.value.authorized)
            } finally { ui.runOnIdle { controller.close() } }
        }
        assertEquals(2, onlineRequests)
        ui.runOnIdle { model.logout() }
        ui.waitUntil(15_000) { model.ui.value.actor.isBlank() }
    }
}
