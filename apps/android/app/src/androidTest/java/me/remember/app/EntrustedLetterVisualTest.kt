package me.remember.app

import android.graphics.Bitmap
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.integration.*
import org.json.JSONObject
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Fictional presentation fixture; never claims an authorized live recipient or real audio. */
class EntrustedLetterVisualTest {
    @get:Rule val ui=createAndroidComposeRule<MainActivity>()
    @Test fun letterUnfoldsWithoutCoveringBodyAndUsesProductionPlayerLayout() {
        val letter=JSONObject().put("id","visual-letter").put("title","厨房那盏小灯").put("author_display_name","陈守义")
            .put("text","你小时候问过，为什么晚回家，厨房里总有一盏灯。\n\n我年轻时跑晚班，回来得迟。你奶奶也会给我留灯。进了门，看见那一点亮，就知道不用再赶路了。\n\n后来轮到我等你。我不想催你，只想让你回来时，能安安稳稳坐下，吃碗热面。")
            .put("audio_id","visual-audio")
        ui.runOnUiThread { ui.activity.setContent { RememberMeTheme(darkTheme=true) {
            CompositionLocalProvider(LocalInteractions provides InteractionContext(reduceMotion=true)) {
                EntrustedLetterSheet(letter,SourcePlayback(),{},{},{})
            }
        } } }
        val inst=InstrumentationRegistry.getInstrumentation()
        val dir=File(ui.activity.getExternalFilesDir(null),"entrusted-letter-visual").apply{mkdirs()}
        fun shot(name:String) { ui.waitForIdle();Thread.sleep(500);val b=inst.uiAutomation.takeScreenshot();File(dir,"$name.png").outputStream().use{b.compress(Bitmap.CompressFormat.PNG,100,it)};b.recycle() }
        ui.waitUntil(10000){ui.onNodeWithText("轻触拆开").isDisplayed()}
        // Wait for the platform dialog window after orientation/density changes as well as Compose.
        Thread.sleep(1500);shot("01-sealed")
        ui.onNodeWithText("轻触拆开").performClick()
        ui.onNodeWithText("厨房那盏小灯").assertIsDisplayed();shot("02-opened")
        ui.onNodeWithContentDescription("播放原音").performScrollTo().assertIsDisplayed();shot("03-player")
        ui.onNodeWithText("陈守义").performScrollTo().assertIsDisplayed()
    }
}
