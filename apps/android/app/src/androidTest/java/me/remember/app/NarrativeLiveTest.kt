package me.remember.app

import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.json.JSONObject
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Opt-in real HTTP test on the isolated evaluation DB; no API mocks/provider keys. */
@RunWith(AndroidJUnit4::class)
class NarrativeLiveTest {
    @get:Rule val ui=createAndroidComposeRule<MainActivity>()
    private fun click(text:String) {
        ui.waitUntil(30_000){ui.onAllNodes(hasText(text) and isEnabled()).fetchSemanticsNodes().isNotEmpty()}
        val node=ui.onAllNodes(hasText(text) and isEnabled()).onFirst()
        if(!node.isDisplayed()) node.performScrollTo()
        ui.waitUntil(30_000){ui.onAllNodes(hasText(text) and isEnabled()).fetchSemanticsNodes().isNotEmpty()}
        node.performClick()
    }
    private fun shot(name:String) {
        File(ui.activity.filesDir,name+".png").outputStream().use { ui.onAllNodes(isRoot()).onLast().captureToImage().asAndroidBitmap().compress(Bitmap.CompressFormat.PNG,100,it) }
    }
    @Test fun reviewedStoryViewsHistoryAndRealAudio() {
        val file=File(ui.activity.filesDir,"narrative-test.json")
        assumeTrue("Explicit local fictional evaluation config required",file.exists())
        val config=JSONObject(file.readText())
        if(ui.onAllNodesWithText("今天").fetchSemanticsNodes().isNotEmpty()) {
            ui.onNodeWithText("我的",useUnmergedTree=true).performClick();click("退出身份")
        }
        click("连接设置 / 开发身份")
        ui.onNodeWithText("共享后端地址").performScrollTo().performTextReplacement(config.getString("url"))
        ui.onNodeWithText("身份凭据").performScrollTo().performTextInput(config.getString("actor_token"))
        click("进入空间")
        ui.waitUntil(30_000){ui.onAllNodesWithText("今天").fetchSemanticsNodes().isNotEmpty()}
        ui.onNodeWithText("档案",useUnmergedTree=true).performClick();click("人物")
        ui.waitUntil(45_000){ui.onAllNodesWithText("慢慢认识一个人").fetchSemanticsNodes().isNotEmpty()}
        click("人生足迹")
        ui.onNodeWithText(config.getString("story_title")).performScrollTo().assertExists()
        shot("round-two-stories")
        click("变化历史")
        ui.waitUntil(30_000){ui.onAllNodesWithText("理解怎样改变").fetchSemanticsNodes().isNotEmpty()}
        shot("round-two-history");click("返回")
        click("重要的人");ui.onNodeWithText("女儿",substring=false).performScrollTo().assertExists()
        click("在意与选择");ui.onNodeWithText("喝茶口味偏好").performScrollTo().assertExists();shot("round-two-understanding")
        click("声音与表达")
        ui.onNodeWithText("允许使用已确认的表达范例；回应仍标明系统生成。").performScrollTo().assertExists()
        click("人生足迹");click("为什么这样整理 · 听原声");click("打开来源与完整原音")
        click("播放完整原音")
        ui.waitUntil(30_000){ui.onAllNodesWithText("暂停").fetchSemanticsNodes().isNotEmpty()}
        click("暂停");ui.onNodeWithText("继续播放").assertExists();shot("round-two-source")
        click("停止播放") // Opening the real player already closes the source dialog.
        ui.onNodeWithText("我的",useUnmergedTree=true).performClick();click("退出身份")
        ui.onNodeWithText("账号").assertExists()
        ui.onNodeWithText(config.getString("story_title")).assertDoesNotExist()
        File(ui.activity.filesDir,"narrative-live-complete").writeText("real HTTP: four views, reviewed story, history, source playback, logout")
    }
}
