package me.remember.app

import android.graphics.Bitmap
import android.view.View
import android.view.ViewGroup
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.integration.NativeWorkbenchModel
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Existing signed-in sample, real ECS; checks layout after Android restoration. */
class SystemBarsRecreationLiveTest {
    @get:Rule val ui = createAndroidComposeRule<MainActivity>()
    private val model get() = ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
    private fun garden() {
        ui.waitUntil(60_000) { model.ui.value.actor.isNotBlank() && !model.ui.value.busy }
        assertTrue("Choose a sample space before this live test", model.ui.value.subject.isNotBlank())
        ui.onNodeWithText("档案").performClick()
        ui.waitForIdle()
        ui.onAllNodesWithText("花田").onFirst().performClick()
        ui.waitForIdle()
    }
    private fun snapshot(name: String): JSONObject {
        Thread.sleep(800)
        val rows = JSONArray()
        fun visit(view: View, depth: Int) {
            val xy = IntArray(2); view.getLocationOnScreen(xy)
            rows.put(JSONObject().put("class",view.javaClass.name).put("x",xy[0]).put("y",xy[1])
                .put("width",view.width).put("height",view.height).put("fits",view.fitsSystemWindows)
                .put("background",view.background?.javaClass?.name))
            if(view.javaClass.name.endsWith("AndroidComposeView")) {
                val owner=generateSequence(view.context) {(it as? android.content.ContextWrapper)?.baseContext}
                    .filterIsInstance<android.app.Activity>().firstOrNull()
                rows.getJSONObject(rows.length()-1).put("contextIsCurrent",owner===ui.activity)
                    .put("contextDestroyed",owner?.isDestroyed).put("windowIsCurrent",owner?.window===ui.activity.window)
            }
            if(view is ViewGroup && depth < 5) for(i in 0 until view.childCount) visit(view.getChildAt(i), depth+1)
        }
        val result = JSONObject()
        ui.activityRule.scenario.onActivity { activity ->
            visit(activity.window.decorView,0)
            @Suppress("DEPRECATION")
            result.put("systemUi",activity.window.decorView.systemUiVisibility)
                .put("statusColor",activity.window.statusBarColor).put("navigationColor",activity.window.navigationBarColor)
                .put("windowFlags",activity.window.attributes.flags).put("views",rows)
            if(android.os.Build.VERSION.SDK_INT >= 30) result.put("fitTypes",activity.window.attributes.fitInsetsTypes)
        }
        val dir=File(ui.activity.getExternalFilesDir(null),"system-bars").apply{mkdirs()}
        val image=InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        File(dir,"$name.png").outputStream().use{image.compress(Bitmap.CompressFormat.PNG,100,it)}
        val sampleX=image.width/3
        val colors=IntArray(8){i -> image.getPixel(sampleX+i*image.width/30, image.height/100)}
        result.put("topPixels",JSONArray(colors.toList()))
        image.recycle()
        File(dir,"$name.json").writeText(result.toString(2))
        return result
    }
    @Test fun gardenKeepsFullWindowBackgroundAfterRecreation() {
        garden(); snapshot("before")
        val subject=model.ui.value.subject
        val owner=model.ui.value.owner
        repeat(3) { round ->
            ui.activityRule.scenario.recreate()
            garden(); val after=snapshot("after-${round+1}")
            assertEquals(subject,model.ui.value.subject)
            assertEquals(owner,model.ui.value.owner)
            val views=after.getJSONArray("views")
            val decor=views.getJSONObject(0)
            val compose=(0 until views.length()).map{views.getJSONObject(it)}.first{it.getString("class").endsWith("AndroidComposeView")}
            assertEquals("Compose background must extend behind the status bar",decor.getInt("y"),compose.getInt("y"))
            assertEquals("Compose background must extend behind the navigation bar",decor.getInt("height"),compose.getInt("height"))
        }
    }
}
