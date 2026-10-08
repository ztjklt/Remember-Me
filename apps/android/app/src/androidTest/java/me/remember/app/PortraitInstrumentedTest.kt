package me.remember.app

import androidx.activity.compose.setContent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.data.local.*
import me.remember.app.feature.PortraitScreen
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PortraitInstrumentedTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private fun observation(id: String, dimension: String, attrs: Map<String, String>) = MemoryObservation(id,
        dimension, "合成$id", "原句$id", "ev", 0, 3, "2026-10-01", "2026-10-08T10:00:00Z", "REPORTED", attrs, "synthetic", "SUBJECT")
    @Test fun allFourViewsAreReachableAndEveryObservationCanOpenItsOriginalSource() {
        val graph = LocalPortrait("synthetic", 1, listOf(PortraitSource("ev", "完整的合成原文", "SUBJECT", "ep")), emptyList(),
            observations = listOf(observation("事件", "event", mapOf("kind" to "HAPPENED", "choice" to "学习", "options" to "学习/薪水", "reason" to "成长")),
                observation("心情", "mood", mapOf("time_scope" to "EVENT", "valence" to "NEGATIVE", "emotion" to "紧张")),
                observation("表达", "expression", mapOf("feature" to "慢慢来"))), status = "READY")
        compose.activity.setContent { RememberMeTheme { PortraitScreen(graph, false, null, {}, {}) } }
        compose.onNodeWithTag("portrait.tab.0").assertExists()
        compose.onNodeWithText("合成事件").assertExists()
        compose.onNodeWithTag("portrait.tab.1").performScrollTo().performClick()
        compose.onNodeWithText("合成心情").assertExists()
        compose.onNodeWithTag("portrait.tab.2").performScrollTo().performClick()
        compose.onNodeWithText("本人选择：学习").assertExists()
        compose.onNodeWithTag("portrait.tab.3").performScrollTo().performClick()
        compose.onNodeWithText("合成表达").assertExists()
        compose.onNodeWithText("查看 1 条依据").performScrollTo().performClick()
        compose.onNodeWithText("完整的合成原文").assertExists()
    }
    @Test fun failedPortraitRetainsReadableOriginalsAndOffersRecovery() {
        val graph = LocalPortrait("synthetic", 1, emptyList(), emptyList(), status = "FAILED")
        compose.activity.setContent { RememberMeTheme { PortraitScreen(graph, false, null, {}, {}, rebuild = {}, pending = true) } }
        compose.onNodeWithText("派生处理失败，原文已保留。下方仅展示已保存观察和上次理解，可继续任务。").assertExists()
        compose.onNodeWithTag("portrait.tab.3").assertExists()
        compose.onNodeWithText("继续任务").assertExists()
    }
}
