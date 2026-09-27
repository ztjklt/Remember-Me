package me.remember.app
import androidx.activity.compose.setContent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.feature.MobileApp
import me.remember.app.feature.MobileViewModel
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
@RunWith(AndroidJUnit4::class)
class MemoriesInstrumentedTest {
    @get:Rule val composeRule = createAndroidComposeRule<MainActivity>()
    @Test fun archiveUpdatesWithoutReopeningAndSearchUsesTranscript() {
        val service=UiTestAudio()
        val model=MobileViewModel(service)
        composeRule.activity.setContent { RememberMeTheme { MobileApp(model) } }
        composeRule.onNodeWithTag("tab.1").performClick()
        composeRule.onNodeWithText("还没有录音").assertExists()
        composeRule.runOnIdle { service.updateRecording(service.saved.copy(transcript="桂花树")) }
        composeRule.onNodeWithText("测试录音").assertExists()
        composeRule.onNodeWithText("搜索标题、文字或记忆").performTextInput("桂花")
        composeRule.onNodeWithText("测试录音").assertExists()
        composeRule.onNodeWithText("搜索标题、文字或记忆").performTextReplacement("不存在")
        composeRule.onNodeWithText("没有找到相关内容").assertExists()
    }
}
