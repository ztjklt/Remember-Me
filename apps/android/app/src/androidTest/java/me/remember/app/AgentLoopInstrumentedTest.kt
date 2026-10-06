package me.remember.app

import androidx.activity.compose.setContent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.data.repository.*
import me.remember.app.feature.AgentScreen
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AgentLoopInstrumentedTest {
    @get:Rule val composeRule = createAndroidComposeRule<MainActivity>()

    @Test fun originalQuestionCorrectionAndUpdatedUnderstandingStayInOneLoop() {
        val data = JSONObject(InstrumentationRegistry.getInstrumentation().context.assets
            .open("agent-loop-http.json").bufferedReader().use { it.readText() })
        var corrected = false
        val gateway = object : AgentGateway {
            override suspend fun request(connection: BackendConnection, path: String, method: String, body: JSONObject?): JSONObject = when {
                path == "/grant" -> JSONObject()
                path == "/model" -> data.getJSONObject(if (corrected) "corrected_model" else "initial_model")
                path == "/evidence" -> JSONObject().put("materials", data.getJSONObject("twin").getJSONArray("evidence"))
                path == "/calibrations" -> JSONObject(data.getJSONObject("locked_calibration").toString()).apply {
                    if (corrected) { put("calibration_id", "cal-new"); getJSONObject("locked_answer").put("revision", 2) }
                }
                path.endsWith("/submit") -> { corrected = true; data.getJSONObject("completed_calibration") }
                else -> error("Unexpected request: $method $path")
            }
        }
        val repo = AgentRepository(gateway)
        val subject = data.getJSONObject("initial_model").getString("subject_id")
        runBlocking { repo.enable(BackendConnection("http://localhost:8000", "test-token", subject, "consent", true)) }
        var captures = 0
        composeRule.activity.setContent { RememberMeTheme { AgentScreen(repo, {}, { captures++ }) } }
        composeRule.onNodeWithTag("agent.original").assertTextEquals(repo.state.value.materials.single().excerpt)
        composeRule.onNodeWithText("当前理解").assertExists()
        composeRule.onNodeWithText(subject, substring = true).assertDoesNotExist()
        composeRule.onNodeWithTag("agent.correctionInput").assertDoesNotExist()
        val question = "工作日下班后喜欢怎么度过？"
        composeRule.onNodeWithTag("agent.question").performScrollTo().performTextInput(question)
        composeRule.onNodeWithTag("agent.ask").performScrollTo().performClick()
        composeRule.waitUntil(timeoutMillis = 20_000) { repo.state.value.calibration?.state == "LOCKED" }
        val locked = repo.state.value.answer
        composeRule.onNodeWithTag("agent.answer").assertTextEquals(locked!!.answer)
        composeRule.onNodeWithTag("agent.correctionInput").performScrollTo().performTextInput("我现在喜欢先和家人聊聊天，再自己待一会儿。")
        composeRule.onNodeWithTag("agent.question").performScrollTo().performTextReplacement("不同的问题")
        composeRule.onNodeWithTag("agent.submit").assertIsNotEnabled()
        composeRule.onNodeWithTag("agent.question").performTextReplacement(question)
        composeRule.onNodeWithTag("agent.submit").performScrollTo().performClick()
        composeRule.waitUntil(timeoutMillis = 20_000) { repo.state.value.snapshot?.revision == 2 && !repo.state.value.busy }
        composeRule.onNodeWithTag("agent.correction").assertTextContains("先和家人聊聊天", substring = true)
        composeRule.onNodeWithTag("agent.answer").assertTextEquals(locked.answer)
        composeRule.onNodeWithText("第 2 版理解").assertExists()
        composeRule.onNodeWithTag("agent.correctionInput").assertDoesNotExist()
        assertEquals(locked, repo.state.value.calibration?.lockedAnswer)
        composeRule.onNodeWithTag("agent.ask").performScrollTo().performClick()
        composeRule.waitUntil(timeoutMillis = 20_000) { repo.state.value.calibration?.id == "cal-new" }
        composeRule.onNodeWithTag("agent.correction").assertDoesNotExist()
        composeRule.onNodeWithText("再录一段，继续循环").performScrollTo().performClick()
        assertEquals(1, captures)
    }
}
