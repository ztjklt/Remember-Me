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

/** Opt-in emulator test against a local, actual cloud-ASR evaluation space.
 * Credentials are injected into app-private storage outside Git; never fixtures
 * pretending to be live network responses. No provider keys enter Android.
 */
@RunWith(AndroidJUnit4::class)
class LiveCloudWorkbenchTest {
    @get:Rule val composeRule = createAndroidComposeRule<MainActivity>()

    @Test fun actualStorySourcePlaybackAndLogout() {
        val context = composeRule.activity.applicationContext
        val credentialFile = File(context.filesDir, "live-cloud-test.json")
        assumeTrue("Explicit live test credentials required", credentialFile.exists())
        val configuration = JSONObject(credentialFile.readText())
        composeRule.onNodeWithText("连接设置 / 开发身份").performScrollTo().performClick()
        composeRule.onNodeWithText("身份凭据").performScrollTo().performTextInput(configuration.getString("actor_token"))
        composeRule.onNodeWithText("进入空间").performClick()
        composeRule.waitUntil(30_000) {
            composeRule.onAllNodesWithText("今天").fetchSemanticsNodes().isNotEmpty()
        }
        composeRule.onNodeWithText("档案", useUnmergedTree = true).performClick()
        composeRule.waitUntil(30_000) {
            composeRule.onAllNodesWithText("打开故事").fetchSemanticsNodes().isNotEmpty()
        }
        // The backend presents newest first; the oldest story is the fixed,
        // completed first cloud sample, while later samples may still process.
        val stories = composeRule.onAllNodesWithText("打开故事")
        (if (configuration.optBoolean("newest")) stories.onFirst() else stories.onLast()).performScrollTo().performClick()
        composeRule.onNodeWithText("转写：" + configuration.optString("expected_model", "relay/codestral-2508"), substring = true).assertExists()
        composeRule.onNodeWithText("播放完整原音").performScrollTo().performClick()
        composeRule.waitUntil(30_000) {
            composeRule.onAllNodesWithText("暂停").fetchSemanticsNodes().isNotEmpty()
        }
        composeRule.onNodeWithText("暂停").performClick()
        composeRule.onNodeWithText("继续播放").assertExists()
        File(context.filesDir, "live-cloud-player.png").outputStream().use {
            composeRule.onRoot().captureToImage().asAndroidBitmap().compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        composeRule.onNodeWithText("继续播放").performClick()
        composeRule.onNodeWithText("停止播放").performClick()
        composeRule.onNodeWithText("我的", useUnmergedTree = true).performClick()
        composeRule.onNodeWithText("退出身份").performScrollTo().performClick()
        composeRule.onNodeWithText("账号").assertExists()
        composeRule.onNodeWithText("停止播放").assertDoesNotExist()
    }
}
