package me.remember.app

import androidx.activity.compose.setContent
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import me.remember.app.data.mock.MockRememberMeRepository
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.feature.MemoriesScreen
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MemoriesInstrumentedTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun injectedRepositoryPreservesMemoryArchiveContentAndBackAction() {
        var backCalls = 0
        val repository = MockRememberMeRepository()

        composeRule.activity.setContent {
            RememberMeTheme { MemoriesScreen(repository) { backCalls++ } }
        }
        composeRule.waitForIdle()

        composeRule.onNodeWithText("Memory Archive").assertExists()
        composeRule.onNodeWithText("不是一份清单，是你留下的人生切片。").assertExists()
        composeRule.onNodeWithText("“那年夏天，我第一次帮外婆整理老照片。她记得每个人拍照时的心情。”").assertExists()
        composeRule.onNodeWithText("“第一次独立完成一部短片以后，我才承认自己真的想做影像。”").assertExists()
        composeRule.onNodeWithText("“搬来杭州不是为了更安稳，而是想把生活过得更诚实一点。”").assertExists()
        composeRule.onNodeWithText("← 返回").performClick()

        assertEquals(1, backCalls)
    }
}
