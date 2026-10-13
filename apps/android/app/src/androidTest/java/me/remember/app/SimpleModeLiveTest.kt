package me.remember.app

import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.integration.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Live ECS workflow. Emulator capture is never labelled a human ASR test. */
class SimpleModeLiveTest {
    @get:Rule val ui = createAndroidComposeRule<MainActivity>()
    private val model get() = ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
    private val auto get() = InstrumentationRegistry.getInstrumentation().uiAutomation
    private fun idle() { ui.waitUntil(90_000) { !model.ui.value.busy }; assertNull(model.ui.value.error) }
    private fun click(label: String) {
        ui.waitUntil(30_000) { ui.onAllNodes(hasText(label) and hasClickAction()).fetchSemanticsNodes().isNotEmpty() }
        val node = ui.onAllNodes(hasText(label) and hasClickAction()).onFirst()
        if(!node.isDisplayed()) node.performScrollTo()
        ui.waitUntil(30_000) { ui.onAllNodes(hasText(label) and isEnabled()).fetchSemanticsNodes().isNotEmpty() }
        ui.onAllNodes(hasText(label) and hasClickAction()).onFirst().performClick()
    }
    private fun shot(name: String) {
        ui.waitForIdle(); Thread.sleep(500)
        val folder = File(ui.activity.getExternalFilesDir(null), "simple-${ui.activity.resources.configuration.fontScale}").apply { mkdirs() }
        val bitmap = auto.takeScreenshot()
        File(folder, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle()
    }
    private fun assertSafeBottom(label: String) {
        val node = ui.onNode(hasText(label) and hasClickAction()).fetchSemanticsNode()
        val bottom = node.positionOnScreen.y + node.size.height
        val metrics = ui.activity.windowManager.currentWindowMetrics
        val safeBottom = metrics.bounds.bottom - metrics.windowInsets.getInsets(android.view.WindowInsets.Type.navigationBars()).bottom
        if(bottom > safeBottom) {
            val views = org.json.JSONArray()
            fun visit(view: android.view.View, depth: Int) {
                val xy=IntArray(2); view.getLocationOnScreen(xy)
                views.put(JSONObject().put("class",view.javaClass.name).put("x",xy[0]).put("y",xy[1])
                    .put("width",view.width).put("height",view.height).put("fits",view.fitsSystemWindows))
                if(view is android.view.ViewGroup && depth<6) for(i in 0 until view.childCount) visit(view.getChildAt(i),depth+1)
            }
            ui.runOnUiThread { android.view.inspector.WindowInspector.getGlobalWindowViews().forEach { visit(it,0) } }
            File(ui.activity.getExternalFilesDir(null),"recorder-window-failure.json").writeText(views.toString(2))
        }
        assertTrue("$label must be fully above gesture area: bottom=$bottom, safeBottom=$safeBottom", bottom <= safeBottom)
    }
    private fun backToStories() {
        ui.waitForIdle()
        ParcelFileDescriptor.AutoCloseInputStream(auto.executeShellCommand("input keyevent KEYCODE_BACK")).use { it.readBytes() }
        try { ui.waitUntil(10_000) { ui.onAllNodesWithText("听故事").fetchSemanticsNodes().isNotEmpty() } }
        catch(error: Throwable) { shot("back-failure"); throw error }
        ui.onNodeWithText("听故事").assertExists()
    }
    @Test fun simpleModeKeepsRealRolesSourcesAndRecording() {
        val cfg = JSONObject(ParcelFileDescriptor.AutoCloseInputStream(auto.executeShellCommand("cat /data/local/tmp/remember-internal-login.json")).bufferedReader().use { it.readText() })
        idle()
        if(model.ui.value.spaceChoiceRequired) { click("退出账号"); ui.waitUntil(15000) { model.ui.value.actor.isBlank() } }
        if(model.ui.value.actor.isNotBlank()) {
            click("我的"); click("账号与空间"); click("退出登录 / 换个账号"); click("确认")
            ui.waitUntil(15000) { model.ui.value.actor.isBlank() }
        }
        ui.onNodeWithText("账号").performScrollTo().performTextInput(cfg.getString("username"))
        ui.onNodeWithText("密码（至少8个字符）").performScrollTo().performTextInput(cfg.getString("password")); click("登录")
        ui.waitUntil(60000) { model.ui.value.actor.isNotBlank() }; idle()
        if(model.ui.value.spaceChoiceRequired) { ui.onNodeWithTag("choose-space-${cfg.getString("subject")}").performClick(); idle() }
        click("我的")
        if(ui.activity.getSharedPreferences("remember-appearance", 0).getBoolean("reduce_motion", false)) {
            click("外观与阅读"); ui.onNode(isToggleable()).performScrollTo().performClick(); click("返回我的")
        }
        if(!ui.activity.getSharedPreferences("remember-appearance", 0).getBoolean("simple_mode", false)) click("简明模式")
        click("今天"); shot("01-home")
        val owner = model.ui.value.owner
        if(owner) {
            click("讲一段故事"); shot("02-recorder"); assertSafeBottom("开始录音")
            auto.grantRuntimePermission(ui.activity.packageName, android.Manifest.permission.RECORD_AUDIO)
            val before = model.ui.value.local.size
            click("开始录音"); ui.waitUntil(10000) { model.ui.value.recording }; Thread.sleep(1600)
            click("暂停"); ui.waitUntil(10000) { model.ui.value.paused }; shot("03-paused"); assertSafeBottom("完成并保存")
            click("继续录音"); ui.waitUntil(10000) { !model.ui.value.paused }; Thread.sleep(1100)
            click("完成并保存"); ui.waitUntil(10000) { !model.ui.value.recording && model.ui.value.local.size == before + 1 }
            shot("04-saved")
            assertTrue(model.ui.value.local.any { it.episode.isBlank() && it.recording.durationMillis > 1000 })
            click("今天"); click("继续整理"); shot("05-pending")
            click("今天"); click("听我的故事")
        } else {
            ui.onNodeWithText("讲一段故事").assertDoesNotExist()
            click("听故事")
        }
        shot("06-stories")
        val episode = cfg.getString("episode")
        ui.onNodeWithTag("simple-play-$episode").performScrollTo()
        ui.waitUntil(30000) { ui.onAllNodes(hasTestTag("simple-play-$episode") and isEnabled()).fetchSemanticsNodes().isNotEmpty() }
        ui.onNodeWithTag("simple-play-$episode").assertIsEnabled().performClick()
        try { ui.waitUntil(30000) { model.ui.value.player.playing && model.ui.value.player.position > 1000 } }
        catch(error: Throwable) {
            shot("playback-failure")
            throw AssertionError("Source playback failed: busy=${model.ui.value.busy}, error=${model.ui.value.error}, player=${model.ui.value.player}",error)
        }
        click("播放控制"); shot("07-player")
        click("暂停原音"); ui.waitUntil(10000) { !model.ui.value.player.playing }
        click("从头再听"); ui.waitUntil(10000) { model.ui.value.player.playing }
        click("停止播放"); click("关闭")
        click("去花田看看"); shot("08-garden")
        val motionBefore = ui.activity.getSharedPreferences("remember-appearance", 0).getBoolean("reduce_motion", false)
        ui.onNodeWithTag("garden-change-scene").performScrollTo().performClick()
        ui.onNodeWithTag("garden-scene-MEADOW").performScrollTo().performClick()
        assertEquals("A temporary simple-mode effect must not change full-mode preferences", motionBefore,
            ui.activity.getSharedPreferences("remember-appearance", 0).getBoolean("reduce_motion", false))
        backToStories()
        click("了解这个人"); backToStories()
        click("今天")
        val subject = model.ui.value.subject
        ui.activityRule.scenario.onActivity { it.viewModelStore.clear() }
        ui.activityRule.scenario.recreate()
        ui.waitUntil(60000) { model.ui.value.actor.isNotBlank() }; idle()
        assertEquals(subject, model.ui.value.subject); assertEquals(owner, model.ui.value.owner)
        ui.onNodeWithText(if(owner) "讲一段故事" else "听故事").assertExists()
        shot("09-restored")
        click("我的"); click("简明模式"); click("今天")
        if(owner) ui.onNodeWithText("讲一段").assertExists() else ui.onNodeWithText("进入花田").assertExists()
        shot("10-full-mode")
        File(ui.activity.getExternalFilesDir(null), "simple-result.json").writeText(JSONObject()
            .put("real_ecs", true).put("owner", owner).put("episodes", model.ui.value.stories.size)
            .put("source_playback", true).put("mode_restored", true).put("font_scale", ui.activity.resources.configuration.fontScale)
            .put("emulator_recording_only", owner).put("human_asr_test", false).put("elder_usability_test", false).toString(2))
    }
}
