package me.remember.app


import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.foundation.layout.*
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.compose.runtime.*
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.integration.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import android.graphics.Bitmap
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File

class ExperiencePolishTest {
    @get:Rule val ui=createAndroidComposeRule<androidx.activity.ComponentActivity>()
    private fun slider()=ui.onNode(SemanticsMatcher.keyIsDefined(SemanticsActions.SetProgress))

    @Test fun twinSpeechKeepsItsActualSourceLabelWhenPlayingOrPaused() {
        var playing by mutableStateOf(true)
        ui.setContent {RememberMeTheme {Surface {
            GardenMiniPlayer(SourcePlayback(episode="answer:saved-answer",playing=playing,duration=120000),{}, {},{})
        }}}
        ui.onNodeWithText("正在听 · AI 分身回答").assertExists()
        ui.onAllNodes(hasText("原音",substring=true)).assertCountEquals(0)
        ui.runOnIdle {playing=false}
        ui.onNodeWithText("AI 分身回答已暂停").assertExists()
    }

    @Test fun draggingPreviewsLocallyAndSeeksOnlyWhenReleased() {
        val seeks=mutableListOf<Long>()
        ui.setContent {RememberMeTheme {Surface {
            GardenMiniPlayer(SourcePlayback(episode="one",duration=120000),{}, {seeks+=it},{})
        }}}
        slider().performTouchInput {down(Offset(width*.2f,centerY));moveTo(center);moveTo(Offset(width*.9f,centerY))}
        assertTrue("The gesture must actually move the thumb",slider().fetchSemanticsNode().config[SemanticsProperties.ProgressBarRangeInfo].current>100000f)
        ui.runOnIdle {assertEquals("Dragging must not repeatedly seek the media player",0,seeks.size)}
        slider().performTouchInput {up()}
        ui.runOnIdle {assertEquals(1,seeks.size);assertTrue(seeks.single()>100000)}
    }

    @Test fun unknownDurationCannotSeekButCanStillStopLoading() {
        var stopped=false
        ui.setContent {RememberMeTheme {Surface {
            GardenMiniPlayer(SourcePlayback(episode="one",preparing=true),{}, {},{stopped=true})
        }}}
        slider().assertIsNotEnabled()
        ui.onNodeWithContentDescription("停止播放").performClick()
        ui.runOnIdle {assertTrue(stopped)}
    }

    @Test fun accessibilityCanSetThePlaybackPosition() {
        var sought=-1L
        ui.setContent {RememberMeTheme {Surface {
            GardenMiniPlayer(SourcePlayback(episode="one",duration=120000),{}, {sought=it},{})
        }}}
        slider().performSemanticsAction(SemanticsActions.SetProgress) {it(60000f)}
        ui.runOnIdle {assertEquals(60000L,sought)}
    }

    @Test fun replacingTheSourceCancelsTheOldGesture() {
        var source by mutableStateOf("one")
        val seeks=mutableListOf<String>()
        ui.setContent {RememberMeTheme {Surface {
            GardenMiniPlayer(SourcePlayback(episode=source,duration=120000),{}, {seeks+=source},{})
        }}}
        slider().performTouchInput {down(Offset(width*.2f,centerY));moveTo(center)}
        assertTrue(slider().fetchSemanticsNode().config[SemanticsProperties.ProgressBarRangeInfo].current>30000f)
        ui.runOnIdle {source="two"}
        slider().performTouchInput {up()}
        ui.runOnIdle {assertTrue("A previous recording's gesture cannot seek the next one",seeks.isEmpty())}
    }

    @Test fun cancellingTheDragDoesNotSeek() {
        var count=0
        ui.setContent {RememberMeTheme {Surface {
            GardenMiniPlayer(SourcePlayback(episode="one",duration=120000),{}, {count++},{})
        }}}
        slider().performTouchInput {down(Offset(width*.2f,centerY));moveTo(center)}
        assertTrue(slider().fetchSemanticsNode().config[SemanticsProperties.ProgressBarRangeInfo].current>30000f)
        slider().performTouchInput {cancel()}
        ui.runOnIdle {assertEquals(0,count)}
    }

    @Test fun loadingDoesNotMoveTheContentAndDisappearsWhenFinished() {
        var busy by mutableStateOf(false)
        ui.setContent {RememberMeTheme {Column {
            RememberLoadingSlot(busy)
            Text("故事仍在这里",Modifier.testTag("anchor"))
        }}}
        val original=ui.onNodeWithTag("anchor").fetchSemanticsNode().boundsInRoot.top
        ui.runOnIdle {busy=true}
        ui.mainClock.advanceTimeBy(300)
        ui.onNodeWithTag("workbench-loading").assertExists()
        assertEquals(original,ui.onNodeWithTag("anchor").fetchSemanticsNode().boundsInRoot.top)
        ui.runOnIdle {busy=false}
        ui.onNodeWithTag("workbench-loading").assertDoesNotExist()
        assertEquals(original,ui.onNodeWithTag("anchor").fetchSemanticsNode().boundsInRoot.top)
    }

    @Test fun aLongErrorHasAReadableDetailAndCanBeDismissed() {
        val message="这次连接没有完成。".repeat(24)
        var error by mutableStateOf<String?>(message)
        ui.setContent {RememberMeTheme {Surface {
            error?.let {RememberIssue(it) {error=null}}
        }}}
        ui.onNodeWithText("查看原因").performClick()
        ui.onNodeWithText("未完成的原因").assertIsDisplayed()
        ui.onNodeWithText("返回").performClick()
        ui.onNodeWithContentDescription("关闭提示").performClick()
        ui.onNodeWithText("这一步没有完成").assertDoesNotExist()
    }

    @Test fun idleAndPausedRecordingStatesDoNotPretendToBeListening() {
        var recording by mutableStateOf(false)
        var paused by mutableStateOf(false)
        ui.setContent {RememberMeTheme {Surface {RememberRecordingStatus(recording,paused,0)}}}
        ui.onNodeWithText("准备好就开始").assertExists()
        ui.onNodeWithText("正在录音").assertDoesNotExist()
        ui.runOnIdle {recording=true}
        ui.onNodeWithText("正在录音").assertExists()
        ui.runOnIdle {paused=true}
        ui.onNodeWithText("已暂停，随时继续").assertExists()
    }

    private fun shot(name:String) {
        ui.waitForIdle()
        Thread.sleep(650)
        val file=File(ui.activity.getExternalFilesDir(null),"experience-review/$name.png").apply {parentFile!!.mkdirs()}
        val bitmap=InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        file.outputStream().use {bitmap.compress(Bitmap.CompressFormat.PNG,100,it)}
        bitmap.recycle()
    }

    @Test fun largeTextAndDarkModeKeepThePlayerOperable() {
        var toggled=false
        var stopped=false
        ui.setContent {RememberMeTheme(darkTheme=true,simpleMode=true) {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density,2f)) {Surface(Modifier.fillMaxSize()) {
                Column(Modifier.safeDrawingPadding().padding(16.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
                    Text("200% 字号 · 播放操作")
                    GardenMiniPlayer(SourcePlayback(episode="one",duration=120000),{toggled=true},{},{stopped=true})
                }
            }}
        }}
        ui.onNodeWithContentDescription("继续播放").assertIsDisplayed().performClick()
        ui.onNodeWithContentDescription("停止播放").assertIsDisplayed().performClick()
        ui.runOnIdle {assertTrue(toggled);assertTrue(stopped)}
        shot("05-large-dark")
    }
}
