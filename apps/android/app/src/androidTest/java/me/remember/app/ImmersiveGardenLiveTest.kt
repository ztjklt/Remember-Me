package me.remember.app

import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.integration.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Actual ECS data only. Kept separate from fixture-based layout tests. */
class ImmersiveGardenLiveTest {
    @get:Rule val ui=createAndroidComposeRule<MainActivity>()
    private val model get()=ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
    private val auto get()=InstrumentationRegistry.getInstrumentation().uiAutomation
    private fun idle(){ui.waitUntil(90_000){!model.ui.value.busy};assertNull(model.ui.value.error)}
    private fun click(text:String){
        ui.waitUntil(30_000){ui.onAllNodes(hasText(text) and isEnabled()).fetchSemanticsNodes().isNotEmpty()}
        // Enabled changes during the server's periodic permission refresh; it is
        // not the node's identity. Reacquire by text after scrolling, then await it.
        val n=ui.onAllNodes(hasText(text)).onFirst();if(!n.isDisplayed())n.performScrollTo()
        ui.waitUntil(30_000){ui.onAllNodes(hasText(text) and isEnabled()).fetchSemanticsNodes().isNotEmpty()}
        ui.onAllNodes(hasText(text)).onFirst().assertIsEnabled().performClick()
    }
    private fun shot(name:String){ui.waitForIdle();Thread.sleep(700)
        val scale=ui.activity.resources.configuration.fontScale
        val dir=File(ui.activity.getExternalFilesDir(null),"immersive-$scale").apply{mkdirs()}
        val b=auto.takeScreenshot();File(dir,"$name.png").outputStream().use{b.compress(Bitmap.CompressFormat.PNG,100,it)};b.recycle()
    }
    @Test fun actualSourceGardenPersonAndLibrary(){
        val cfg=JSONObject(ParcelFileDescriptor.AutoCloseInputStream(auto.executeShellCommand("cat /data/local/tmp/remember-internal-login.json")).bufferedReader().use{it.readText()})
        idle()
        if(model.ui.value.actor.isNotBlank()){click("我的");click("账号与空间");click("退出登录 / 换个账号");click("确认");ui.waitUntil(15000){model.ui.value.actor.isBlank()}}
        ui.onNodeWithText("账号").performScrollTo().performTextInput(cfg.getString("username"))
        ui.onNodeWithText("密码（至少8个字符）").performScrollTo().performTextInput(cfg.getString("password"));click("登录")
        ui.waitUntil(60_000){model.ui.value.actor.isNotBlank()||model.ui.value.error!=null};idle()
        if(cfg.optString("subject").isNotBlank() && model.ui.value.subject!=cfg.getString("subject")) {
            val current=model.ui.value.space!!
            click(current.text("display_name")+" · "+if(model.ui.value.owner) "记录者" else "授权读者")
            val target=model.ui.value.spaces.first{it.text("subject_id")==cfg.getString("subject")}
            click(target.text("display_name")+" · "+target.text("role"));idle()
        }
        assertEquals("paraformer-v2",model.ui.value.asrCapabilities?.optString("stt_model"))
        assertTrue(model.ui.value.stories.any{it.optString("episode_id")==cfg.getString("episode")})
        shot("01-today")
        if(model.ui.value.owner){
            click("讲一段");ui.onNodeWithText("开始录音").assertIsDisplayed();shot("02-recorder-entry")
            val before=model.ui.value.local.size
            // Emulator microphone capture smoke: not evidence of human speech/ASR quality.
            auto.grantRuntimePermission(ui.activity.packageName,android.Manifest.permission.RECORD_AUDIO)
            click("开始录音");ui.waitUntil(10000){model.ui.value.recording};Thread.sleep(1500)
            click("暂停");ui.waitUntil(10000){model.ui.value.paused};shot("02b-recorder-paused")
            click("继续录音");ui.waitUntil(10000){!model.ui.value.paused};Thread.sleep(1200)
            click("完成并保存");ui.waitUntil(10000){!model.ui.value.recording&&model.ui.value.local.size==before+1}
            assertTrue(model.ui.value.local.any{it.recording.durationMillis>1000})
        }
        click("档案");click("花田");idle();shot("03-garden")
        val cluster=projectGarden(model.ui.value.stories,model.ui.value.narrative).first{cfg.getString("episode") in it.episodeIds}
        ui.onNodeWithTag("garden-cluster-${cluster.id}").performScrollTo().performClick();shot("04-flower")
        val petal=cluster.petals.first();click(petal.title);ui.mainClock.advanceTimeBy(800);ui.waitUntil(10000){ui.onAllNodesWithTag("garden-source-play").fetchSemanticsNodes().isNotEmpty()};shot("05-memory-source")
        idle()
        ui.onNodeWithTag("garden-source-play").assertIsEnabled().performClick()
        try { ui.waitUntil(30000){model.ui.value.player.playing && model.ui.value.player.position>1000} }
        catch(error:Throwable) {
            shot("playback-failure")
            throw AssertionError("Playback did not start: busy=${model.ui.value.busy}, error=${model.ui.value.error}, player=${model.ui.value.player}",error)
        }
        ui.onNodeWithTag("garden-source-play").assertIsEnabled().performClick()
        ui.waitUntil(10000){!model.ui.value.player.playing};assertFalse(model.ui.value.player.playing);shot("06-playback")
        click("返回花朵");click("返回花田")
        ui.waitUntil(10000){ui.onNodeWithTag("garden-cluster-${cluster.id}").isDisplayed()}
        ui.onNodeWithContentDescription("停止播放").performClick()
        click("列表");shot("06b-list")
        click("查找");ui.onNodeWithText("找故事、人物或一句话").performTextInput("王建国")
        click("查找相关内容");idle();assertTrue(model.ui.value.search.isNotEmpty());shot("06c-search")
        ui.onNodeWithText("找故事、人物或一句话").performTextClearance()
        click("人物");shot("07-person")
        personViewTitles.forEachIndexed { i,title -> click(title);shot("08-view-$i") }
        click("记忆侧面");shot("09-sides")
        click("查找内容");ui.onNodeWithText("人名、故事或一句话").performScrollTo().performTextInput("陈岚")
        val person=model.ui.value.narrative.rows("records").first{it.text("kind")=="person"&&it.text("title")=="陈岚"&&it.text("status")=="confirmed"}
        ui.onNodeWithTag("narrative-result-${person.text("id")}").performScrollTo().assertIsDisplayed()
        shot("09b-side-search")
        click("全部录音");shot("10-library")
        if(model.ui.value.owner) {
            idle();click("打开故事");idle();click("用新录音补充、纠正或说明变化")
            ui.onNodeWithText("取消关联，记录新故事").assertExists()
            ui.onNodeWithContentDescription("关闭录音").performClick()
            click("今天");click("讲一段")
            ui.onNodeWithText("取消关联，记录新故事").assertDoesNotExist()
            ui.onNodeWithContentDescription("关闭录音").performClick()
        }
        File(ui.activity.getExternalFilesDir(null),"immersive-result.json").writeText(JSONObject()
            .put("real_ecs",true).put("episodes",model.ui.value.stories.size).put("playback",true)
            .put("font_scale",ui.activity.resources.configuration.fontScale).put("physical_phone",false).toString(2))
    }
}
