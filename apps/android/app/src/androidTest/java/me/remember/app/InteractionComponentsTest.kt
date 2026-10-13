package me.remember.app

import android.graphics.Bitmap
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.Lifecycle
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.integration.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Isolated component checks; no backend, account, microphone or model calls. */
class InteractionComponentsTest {
    @get:Rule val ui=createAndroidComposeRule<androidx.activity.ComponentActivity>()
    private fun show(simple: Boolean=false, reduced: Boolean=false, content: @Composable () -> Unit) {
        ui.setContent { RememberMeTheme(simpleMode=simple) {
            CompositionLocalProvider(LocalInteractions provides InteractionContext(reduceMotion=reduced)) { Surface {content()} }
        } }
    }
    private fun shot(name:String) {
        ui.waitForIdle()
        Thread.sleep(650) // Window/surface transitions run outside Compose's test clock.
        val file=File(ui.activity.getExternalFilesDir(null),"interaction-review/$name.png").apply {parentFile!!.mkdirs()}
        val bitmap=InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        file.outputStream().use {bitmap.compress(Bitmap.CompressFormat.PNG,100,it)}
        bitmap.recycle()
    }
    @Test fun waitingIsNotSuccessAfterTheReferenceAnimationsTimer() {
        var op by mutableStateOf(OperationFeedback())
        var requests=0
        show { CompositionLocalProvider(LocalInteractions provides InteractionContext(operation=op,latest={op})) {
            RememberActionButton("整理",op.phase!=ActionPhase.RUNNING,successLabel="已提交整理") {requests++;op=OperationFeedback(1,ActionPhase.RUNNING)}
        } }
        ui.onNodeWithText("整理").performClick()
        Thread.sleep(1600)
        ui.onNodeWithText("整理 · 正在提交…").assertIsNotEnabled()
        ui.onAllNodes(hasText("已提交整理",substring=true)).assertCountEquals(0)
        ui.runOnIdle {assertEquals(1,requests);op=op.copy(phase=ActionPhase.SUCCEEDED)}
        ui.onNodeWithText("整理 · 已提交整理").assertExists()
    }
    @Test fun failedRequestOffersRetryAndKeepsFailureVisible() {
        var op by mutableStateOf(OperationFeedback())
        var requests=0
        show { CompositionLocalProvider(LocalInteractions provides InteractionContext(operation=op,latest={op})) {
            RememberActionButton("提问") {requests++;op=OperationFeedback(requests.toLong(),ActionPhase.RUNNING)}
        } }
        ui.onNodeWithText("提问").performClick()
        ui.runOnIdle {op=op.copy(phase=ActionPhase.FAILED)}
        ui.onNodeWithText("提问 · 未完成 · 重试").performClick()
        ui.runOnIdle {assertEquals(2,requests)}
        ui.onNodeWithText("提问 · 正在提交…").assertIsNotEnabled()
    }
    @Test fun newIdentityCannotKeepThePreviousPersonsButtonReceipt() {
        var identity by mutableStateOf("owner")
        var op by mutableStateOf(OperationFeedback())
        show { CompositionLocalProvider(LocalInteractions provides InteractionContext(identity,op,{op})) {
            RememberActionButton("整理") {op=OperationFeedback(1,ActionPhase.RUNNING)}
        } }
        ui.onNodeWithText("整理").performClick()
        ui.runOnIdle {identity="reader";op=OperationFeedback(1,ActionPhase.SUCCEEDED)}
        ui.onNodeWithText("整理").assertExists()
        ui.onAllNodes(hasText("已提交",substring=true)).assertCountEquals(0)
    }
    @Test fun toggleWaitsForActualCheckedStateAndHasOneAccessibleTarget() {
        var checked by mutableStateOf(false)
        var requested=false
        show { RememberToggle("每日提醒",checked,{requested=it}) }
        val node=ui.onNodeWithText("每日提醒")
        node.assertIsOff().assert(SemanticsMatcher.expectValue(SemanticsProperties.Role,Role.Switch)).performClick()
        node.assertIsOff()
        ui.runOnIdle {assertTrue(requested);checked=true}
        node.assertIsOn()
        ui.onAllNodes(SemanticsMatcher.expectValue(SemanticsProperties.Role,Role.Switch)).assertCountEquals(1)
    }
    @Test fun remoteToggleDisablesUntilResponseAndDoesNotPretendFailureSaved() {
        var op by mutableStateOf(OperationFeedback())
        var checked by mutableStateOf(false)
        var requests=0
        show {CompositionLocalProvider(LocalInteractions provides InteractionContext(operation=op,latest={op})) {
            RememberToggle("允许问答参考",checked,{requests++;op=OperationFeedback(requests.toLong(),ActionPhase.RUNNING)})
        }}
        ui.onNodeWithText("允许问答参考").performClick().assertIsOff().assertIsNotEnabled()
        ui.runOnIdle {assertEquals(1,requests);op=op.copy(phase=ActionPhase.FAILED)}
        ui.onNodeWithText("允许问答参考").assertIsOff().assertIsEnabled().performClick()
        ui.runOnIdle {assertEquals(2,requests);checked=true;op=op.copy(phase=ActionPhase.SUCCEEDED)}
        ui.onNodeWithText("允许问答参考").assertIsOn()
    }
    @Test fun confirmedActionHasNoSuccessUntilTheActualConfirmedRequestReturns() {
        var op by mutableStateOf(OperationFeedback())
        var requests=0
        show(simple=true) {CompositionLocalProvider(LocalInteractions provides InteractionContext(operation=op,latest={op})) {
            RememberConfirmedAction("撤回补记","撤回这段补记？",true,successLabel="已撤回") {
                requests++;op=OperationFeedback(requests.toLong(),ActionPhase.RUNNING)
            }
        }}
        ui.onNodeWithText("撤回补记").performClick()
        ui.runOnIdle {assertEquals(0,requests)}
        ui.onNodeWithText("取消").performClick()
        ui.runOnIdle {assertEquals(0,requests)}
        ui.onNodeWithText("撤回补记").performClick();ui.onNodeWithText("确认").performClick()
        ui.onNodeWithText("撤回补记 · 正在提交…").assertIsNotEnabled()
        ui.runOnIdle {assertEquals(1,requests);op=op.copy(phase=ActionPhase.SUCCEEDED)}
        ui.onNodeWithText("撤回补记 · 已撤回").assertExists()
    }
    @Test fun earlyReleaseDoesNotConfirm() {
        var count=0
        show {RememberConfirmationDialog("撤销这段授权？",true,dismiss={},confirm={count++})}
        ui.onNodeWithTag("hold-confirm").performTouchInput {down(center)}
        Thread.sleep(180)
        ui.onNodeWithTag("hold-confirm").performTouchInput {up()}
        Thread.sleep(1700)
        ui.runOnIdle {assertEquals(0,count)}
    }
    @Test fun fullHoldCommitsOnlyOnce() {
        var count=0
        show {RememberConfirmationDialog("撤销这段授权？",true,dismiss={},confirm={count++})}
        ui.onNodeWithTag("hold-confirm").performTouchInput {down(center)}
        ui.waitUntil(5000) {count==1}
        ui.onNodeWithTag("hold-confirm").performTouchInput {up()}
        ui.onNodeWithText("确认").assertIsNotEnabled()
        ui.runOnIdle {assertEquals(1,count)}
    }
    @Test fun movingIntoBackgroundCancelsAHold() {
        var count=0
        show {RememberConfirmationDialog("撤销这段授权？",true,dismiss={},confirm={count++})}
        ui.onNodeWithTag("hold-confirm").performTouchInput {down(center)}
        ui.activityRule.scenario.moveToState(Lifecycle.State.STARTED)
        Thread.sleep(1700)
        ui.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
        ui.runOnIdle {assertEquals(0,count)}
    }
    @Test fun reducedMotionDoesNotShortenTheSafetyHold() {
        var count=0
        show(reduced=true) {RememberConfirmationDialog("撤销这段授权？",true,dismiss={},confirm={count++})}
        ui.onNodeWithTag("hold-confirm").performTouchInput {down(center)}
        Thread.sleep(150)
        ui.onNodeWithTag("hold-confirm").performTouchInput {up()}
        ui.runOnIdle {assertEquals(0,count)}
    }
    @Test fun draggingOutsideCancelsWithoutConfirming() {
        var count=0
        show {RememberConfirmationDialog("撤销这段授权？",true,dismiss={},confirm={count++})}
        ui.onNodeWithTag("hold-confirm").performTouchInput {down(center);moveTo(Offset(-180f,-180f));up()}
        Thread.sleep(1600)
        ui.runOnIdle {assertEquals(0,count)}
    }
    @Test fun largeTextAndDarkThemeKeepSettingsAndConfirmationReachable() {
        ui.setContent {RememberMeTheme(darkTheme=true,simpleMode=true) {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density,2f)) {
                Column {
                    RememberToggle("减少动态效果",true,{},Modifier.testTag("large-switch"))
                    RememberActionButton("确认文字并整理",modifier=Modifier.testTag("large-button")) {}
                }
            }
        } }
        ui.onNodeWithTag("large-switch").assertIsDisplayed().assertIsOn()
        ui.onNodeWithTag("large-button").assertIsDisplayed().performClick()
        shot("07-large-dark")
    }
    @Test fun simpleModeUsesOrdinaryConfirmationWithoutAHold() {
        var count=0
        show(simple=true) {RememberConfirmationDialog("撤销这段授权？",true,dismiss={},confirm={count++})}
        ui.onNodeWithTag("hold-confirm").assertDoesNotExist()
        ui.onNodeWithText("确认").performClick()
        ui.runOnIdle {assertEquals(1,count)}
        shot("04-simple-confirmation")
    }
}
