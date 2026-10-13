package me.remember.app

import android.Manifest
import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Real native MediaRecorder, injected fictional audio, cloud ASR/LLM; opt-in only. */
@RunWith(AndroidJUnit4::class)
class MobileProductLiveTest {
    @get:Rule val ui = createAndroidComposeRule<MainActivity>()
    private fun click(text: String) {
        ui.waitUntil(30_000) { ui.onAllNodes(hasText(text) and isEnabled()).fetchSemanticsNodes().isNotEmpty() }
        val node=ui.onAllNodesWithText(text).onFirst()
        if(!node.isDisplayed()) node.performScrollTo()
        node.performClick()
    }
    private fun tab(text: String) = ui.onNodeWithText(text, useUnmergedTree = true).performClick()
    private fun check(label: String) = ui.onAllNodes(isToggleable() and hasAnySibling(hasText(label, substring = true))).onFirst().performScrollTo().performClick()
    private fun screenshot(name: String) {
        File(ui.activity.filesDir, name+".png").outputStream().use { ui.onRoot().captureToImage().asAndroidBitmap().compress(Bitmap.CompressFormat.PNG,100,it) }
    }
    @Test fun nativeRecordingToCloudMemoryAndTwin() {
        val file=File(ui.activity.filesDir,"mobile-product-config.json")
        assumeTrue("Explicit live credentials and virtual mic injector required",file.exists())
        val config=JSONObject(file.readText())
        InstrumentationRegistry.getInstrumentation().uiAutomation.grantRuntimePermission(ui.activity.packageName, Manifest.permission.RECORD_AUDIO)
        if(ui.onAllNodesWithText("今天").fetchSemanticsNodes().isNotEmpty()) { tab("我的");click("退出身份") }
        screenshot("product-login")
        ui.onNodeWithText("账号").performTextInput(config.getString("username"))
        ui.onNodeWithText("密码（至少10个字符）").performTextInput(config.getString("password"))
        click("登录")
        ui.waitUntil(45_000) { ui.onAllNodesWithText("开始录音").fetchSemanticsNodes().isNotEmpty() }
        screenshot("product-today")
        tab("我的")
        ui.onNodeWithText("人名、方言与含义").performScrollTo().performTextReplacement(config.getString("supplement"))
        click("保存我的用词")
        ui.waitForIdle();tab("今天")
        if(ui.onAllNodesWithText("播放本机原音").fetchSemanticsNodes().isEmpty()) {
        check("我同意本次麦克风录音")
        click("开始录音")
        ui.waitUntil(15_000) { ui.onAllNodesWithText("暂停录音").fetchSemanticsNodes().isNotEmpty() }
        click("暂停录音");click("继续录音")
        File(ui.activity.filesDir,"mobile-audio-start").writeText("inject fictional TTS now")
        ui.waitUntil(70_000) { File(ui.activity.filesDir,"mobile-audio-done").exists() }
        click("停止并保留原音")
        ui.waitUntil(15_000) { ui.onAllNodesWithText("播放本机原音").fetchSemanticsNodes().isNotEmpty() }
        }
        click("播放本机原音")
        ui.waitUntil(15_000) { ui.onAllNodesWithText("停止本机播放").fetchSemanticsNodes().isNotEmpty() }
        click("停止本机播放")
        check("同意保存原音，并将本段完整音频")
        click("上传并等待核对")
        ui.waitUntil(30_000) { ui.onAllNodesWithText("已上传 · ",substring=true).fetchSemanticsNodes().isNotEmpty() }
        tab("档案")
        ui.waitUntil(120_000) { ui.onAllNodesWithText("待核对文字",substring=true).fetchSemanticsNodes().isNotEmpty() }
        click("核对转写")
        ui.waitUntil(15_000) { ui.onAllNodesWithText("核对后的文字").fetchSemanticsNodes().isNotEmpty() }
        click("带入我的用词")
        // Technical confirmation of actual ASR, never replaced with the TTS script.
        check("我确认文字与补充说明")
        click("确认文字并整理")
        ui.waitUntil(120_000) { ui.onAllNodesWithText(" · ready",substring=true).fetchSemanticsNodes().isNotEmpty() }
        screenshot("product-stories")
        click("打开故事")
        ui.onNodeWithText("本人书面补充 · 不属于录音原话").performScrollTo().assertExists()
        click("关闭")
        tab("对话")
        ui.onNodeWithText("想了解什么？").performTextInput("我说的落屋是什么意思？老隗是亲戚吗？")
        check("同意本次将问题和有权访问")
        click("提问")
        ui.waitUntil(90_000) { ui.onAllNodesWithText("模型：Deepseek-v4-flash",substring=true).fetchSemanticsNodes().isNotEmpty() }
        ui.onNodeWithText("依据记录生成 · 不是本人原话").performScrollTo().assertExists()
        screenshot("product-twin")
        File(ui.activity.filesDir,"mobile-product-complete").writeText("native recording, source playback, review supplement, cloud memory, Twin completed")
    }
    @Test fun persistedSessionPortraitAndLogout() {
        assumeTrue(File(ui.activity.filesDir,"mobile-product-complete").exists())
        ui.waitUntil(45_000) { ui.onAllNodesWithText("今天").fetchSemanticsNodes().isNotEmpty() }
        tab("档案");click("人物")
        ui.waitUntil(45_000) { ui.onAllNodesWithText("在意与选择").fetchSemanticsNodes().isNotEmpty() }
        ui.onNodeWithText("在意与选择").performScrollTo().assertExists()
        screenshot("product-portrait")
        tab("我的");click("退出身份")
        ui.waitUntil(15_000) { ui.onAllNodesWithText("账号").fetchSemanticsNodes().isNotEmpty() }
        org.junit.Assert.assertNull(me.remember.app.integration.SavedSession(ui.activity).load())
    }
}
