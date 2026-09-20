package me.remember.app

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalTestApi::class)
class OnboardingSmokeTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun onboardingReachesCreatorHome() {
        composeRule.waitUntilAtLeastOneExists(hasText("开始"), 3_000)
        composeRule.onNodeWithText("开始").performClick()
        composeRule.onNodeWithText("继续").performClick()
        composeRule.onNodeWithText("同意并继续").performClick()
        composeRule.onNodeWithText("开始说").performClick()
        composeRule.onNodeWithText("停止").performClick()
        composeRule.waitUntilAtLeastOneExists(hasText("我开始认识你了。"), 6_000)
        composeRule.onNodeWithText("继续").performClick()
        composeRule.onNodeWithText("进入 Remember Me").performClick()
        composeRule.onNodeWithText("今天想留下些什么？").assertExists()
    }
}
