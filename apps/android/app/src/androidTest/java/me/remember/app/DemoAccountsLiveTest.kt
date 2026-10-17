package me.remember.app

import android.content.Intent
import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.integration.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Uses the opt-in fictional demo service. No password or fabricated story fixture. */
class DemoAccountsLiveTest {
    @get:Rule val ui = createEmptyComposeRule()
    @Test fun freshStartSwitchAndRestoreDistinctAccounts() {
        val inst = InstrumentationRegistry.getInstrumentation()
        val context = inst.targetContext
        assertTrue(BuildConfig.DEMO_ACCOUNTS)
        // An upgrade must discard an old test login before any old-space request.
        SavedSession(context).save(BuildConfig.SERVICE_URL, "retired-test-session-must-not-be-restored")
        context.getSharedPreferences("remember-spaces",0).edit().putBoolean("manual-login",true)
            .remove("chen-demo-generation").putString("demo-role","relative").commit()
        val folder = File(context.getExternalFilesDir(null),"demo-accounts-live").apply { mkdirs() }
        fun shot(name: String) { ui.waitForIdle(); Thread.sleep(500); val b=inst.uiAutomation.takeScreenshot();File(folder,"$name.png").outputStream().use{b.compress(Bitmap.CompressFormat.PNG,100,it)}; b.recycle() }
        fun click(text: String) {
            val node=ui.onAllNodes(hasText(text) and hasClickAction()).onFirst()
            if(!node.isDisplayed()) node.performScrollTo()
            node.performClick()
        }
        lateinit var model: NativeWorkbenchModel
        fun ready(role: String) { ui.waitUntil(90000) { !model.ui.value.busy && model.ui.value.demoRole==role && model.ui.value.subject.isNotBlank() };assertNull(model.ui.value.error) }
        val report = JSONObject().put("real_backend",true).put("version",BuildConfig.VERSION_NAME)
        var scenario=ActivityScenario.launch<MainActivity>(Intent(context,MainActivity::class.java))
        try {
            scenario.onActivity { model=ViewModelProvider(it)[NativeWorkbenchModel::class.java] }
            ready("owner");assertTrue(model.ui.value.owner)
            val owner=model.ui.value.actor
            val ownerStories=model.ui.value.stories.map { it.text("episode_id") }.toSet()
            ui.onNodeWithText("陈守义 · 本人").assertIsDisplayed()
            ui.onAllNodesWithText("录音豆", substring=true).onFirst().assertIsDisplayed();shot("01-owner")
            click("我的");click("我的账号");ui.onNodeWithTag("demo-account-relative").assertIsDisplayed();shot("02-switch")
            ui.onNodeWithText("使用其他账号").assertDoesNotExist()
            ui.onNodeWithTag("demo-account-relative").performClick()
            ready("relative");assertFalse(model.ui.value.owner);assertNotEquals(owner,model.ui.value.actor)
            val relative=model.ui.value.actor
            val shared=model.ui.value.stories.map { it.text("episode_id") }.toSet()
            assertTrue(ownerStories.containsAll(shared));assertTrue(shared.size<ownerStories.size)
            assertTrue(model.ui.value.local.isEmpty());assertEquals("",model.ui.value.player.episode);assertNull(model.voiceCall.value)
            ui.onNodeWithText("女儿 · 亲友").assertIsDisplayed()
            ui.onNodeWithText("聊一聊").assertIsDisplayed();shot("03-relative-chat")
            click("档案");ui.onNodeWithTag("garden-unopened").assertIsDisplayed();shot("04-relative-garden")
            click("我的");ui.onNodeWithText("连接录音豆").assertDoesNotExist()
            scenario.close()
            scenario=ActivityScenario.launch<MainActivity>(Intent(context,MainActivity::class.java))
            scenario.onActivity { model=ViewModelProvider(it)[NativeWorkbenchModel::class.java] }
            ready("relative");assertEquals(relative,model.ui.value.actor);shot("05-restored-relative")
            click("我的");click("我的账号");ui.onNodeWithTag("demo-account-owner").performClick()
            ready("owner");assertEquals(owner,model.ui.value.actor);assertTrue(model.ui.value.owner)
            assertEquals(ownerStories,model.ui.value.stories.map { it.text("episode_id") }.toSet());shot("06-back-owner")
            report.put("fresh_owner",true).put("different_actors",true).put("relative_subset",true)
                .put("old_login_migrated",true).put("demo_only_entry",true)
                .put("owner_story_count",ownerStories.size).put("relative_story_count",shared.size)
                .put("restore_relative",true).put("back_owner",true).put("no_relative_recorder",true).put("ok",true)
        } finally { File(folder,"report.json").writeText(report.toString(2)); scenario.close() }
    }
}
