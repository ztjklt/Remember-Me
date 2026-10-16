package me.remember.app

import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.integration.NativeWorkbenchModel
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Read-only cloud login/navigation with a separately supplied fictional demo account. */
class HardwareScreenSmokeTest {
    @get:Rule val ui = createAndroidComposeRule<MainActivity>()
    @Test fun ownerCanOpenDevicePage() {
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        val cfg = JSONObject(ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand("cat /data/local/tmp/remember-hardware-login.json")).bufferedReader().use { it.readText() })
        val model = ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
        ui.runOnIdle { model.signIn("https://39.108.183.47", cfg.getString("username"), cfg.getString("password")) }
        ui.waitUntil(60_000) { model.ui.value.actor.isNotBlank() && !model.ui.value.busy || model.ui.value.error != null }
        assertNull(model.ui.value.error)
        assertTrue(model.ui.value.owner)
        lateinit var retained: me.remember.app.hardware.Work3200Controller
        ui.runOnIdle { retained = model.recorder() }
        fun click(text: String) {
            val node = ui.onAllNodes(hasText(text) and hasClickAction()).onFirst()
            if (!node.isDisplayed()) node.performScrollTo()
            node.performClick()
        }
        ui.onNodeWithText("录音豆录音").assertExists()
        click("我的"); click("连接录音豆")
        ui.runOnIdle { assertSame(retained, model.recorder()) }
        ui.onNodeWithText("准备连接").assertExists()
        ui.onNode(hasText("手机已保存：", substring = true)).assertExists()
        ui.onNodeWithText("准备连接").performScrollTo()
        ui.waitForIdle()
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        Thread.sleep(500) // Wait for the compositor after Compose's semantics have settled.
        val screenshot = automation.takeScreenshot()
        File(ui.activity.getExternalFilesDir(null), "hardware-page-smoke.png").outputStream().use { screenshot.compress(Bitmap.CompressFormat.PNG, 100, it) }
        screenshot.recycle()
        click("今天")
        ui.onNodeWithText("录音豆录音").assertExists()
        ui.runOnIdle { assertSame(retained, model.recorder()) }
        click("手机")
        ui.onNodeWithText("用手机讲一段").assertExists()
        click("录音豆")
        ui.runOnIdle { model.logout() }
        ui.waitUntil(15_000) { model.ui.value.actor.isBlank() }
    }
}
