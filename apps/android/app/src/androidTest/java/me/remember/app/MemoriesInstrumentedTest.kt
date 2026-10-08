package me.remember.app

import androidx.activity.compose.setContent
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import me.remember.app.data.mock.MockRememberMeRepository
import me.remember.app.data.repository.EpisodeMemoryRepository
import me.remember.app.data.repository.EpisodeResult
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.feature.MemoriesScreen
import me.remember.app.model.Memory
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

        composeRule.onNodeWithText("我的记忆").assertExists()
        composeRule.onNodeWithText("资料来源：电脑服务").assertExists()
        composeRule.onNodeWithText("“那年夏天，我第一次帮外婆整理老照片。她记得每个人拍照时的心情。”").assertExists()
        composeRule.onNodeWithText("“第一次独立完成一部短片以后，我才承认自己真的想做影像。”").assertExists()
        composeRule.onNodeWithText("“搬来杭州不是为了更安稳，而是想把生活过得更诚实一点。”").assertExists()
        composeRule.onNodeWithText("← 返回").performClick()

        assertEquals(1, backCalls)
    }

    @Test
    fun backendMemoryShowsProvenanceWithoutFakeAudioPlayer() {
        val repository = EpisodeMemoryRepository().apply {
            show(EpisodeResult("episode-1", "fixture-ai-v2", listOf(
                Memory(
                    id = "episode-1:0", date = "", place = "", story = "真实提取的记忆",
                    people = emptyList(), tags = emptyList(), duration = "",
                    episodeId = "episode-1", memoryType = "EVENT", sourceType = "AI_INFERENCE",
                    evidenceIds = listOf("ev-1"), confidence = 0.75,
                    modelVersion = "fixture-ai-v2", hasPlayableAudio = false
                )
            )))
        }
        composeRule.activity.setContent {
            RememberMeTheme { MemoriesScreen(repository) {} }
        }

        composeRule.onNodeWithText("“真实提取的记忆”").assertExists()
        composeRule.onNodeWithText("Episode：episode-1").assertExists()
        composeRule.onNodeWithText("证据：ev-1").assertExists()
        composeRule.onNodeWithText("2012 · 襄阳").assertDoesNotExist()
        composeRule.onNodeWithText("00:42").assertDoesNotExist()
    }
}
