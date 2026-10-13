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
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.io.File

/** One phase per device. Host coordinates two independent emulator data stores.
 * Explicit ordinary test accounts only; no password/token in runner arguments.
 */
class PairedDevicesLiveTest {
    @get:Rule val ui=createAndroidComposeRule<MainActivity>()
    private val model get()=ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
    private fun idle(){ui.waitUntil(90_000){!model.ui.value.busy};assertNull(model.ui.value.error)}
    private fun click(text:String){
        val matcher=hasText(text) and isEnabled()
        ui.waitUntil(30_000){ui.onAllNodes(matcher).fetchSemanticsNodes().isNotEmpty()}
        val node=ui.onAllNodes(matcher).onFirst()
        if(!node.isDisplayed())node.performScrollTo()
        node.performClick()
    }
    private fun tab(text:String){
        ui.waitUntil(30_000){ui.onAllNodesWithText(text,useUnmergedTree=true).fetchSemanticsNodes().isNotEmpty()}
        ui.onNodeWithText(text,useUnmergedTree=true).performClick()
    }
    private fun toggle(tag:String){
        val matcher=hasTestTag(tag) and isEnabled()
        ui.waitUntil(30_000){ui.onAllNodes(matcher).fetchSemanticsNodes().isNotEmpty()}
        ui.onAllNodes(matcher).onFirst().performScrollTo().performClick()
    }
    @Test fun devicePhase(){
        val fd=InstrumentationRegistry.getInstrumentation().uiAutomation.executeShellCommand("cat /data/local/tmp/remember-paired-device.json")
        val raw=ParcelFileDescriptor.AutoCloseInputStream(fd).bufferedReader().use{it.readText()}
        assumeTrue(raw.trim().startsWith("{"))
        val cfg=JSONObject(raw);val person=cfg.getJSONObject("account")
        val subject=cfg.getString("subject");val episode=cfg.getString("episode");val phase=cfg.getString("phase")
        val url=cfg.optString("url",BuildConfig.SERVICE_URL)
        require(BuildConfig.DEBUG || url==BuildConfig.SERVICE_URL)
        idle()
        if(model.ui.value.actor!=person.getString("actor_id")){
            if(model.ui.value.actor.isNotBlank()){tab("我的");click("退出身份");idle()}
            if(url!=BuildConfig.SERVICE_URL){click("连接设置 / 开发身份");ui.onNodeWithText("共享后端地址").performScrollTo().performTextReplacement(url)}
            ui.onNodeWithText("账号").performScrollTo().performTextReplacement(person.getString("username"))
            ui.onNodeWithText("密码（至少10个字符）").performScrollTo().performTextInput(person.getString("password"))
            click("登录")
            ui.waitUntil(90_000){model.ui.value.actor==person.getString("actor_id") && !model.ui.value.busy || model.ui.value.error!=null}
            idle()
        }
        assertEquals(person.getString("actor_id"),model.ui.value.actor)
        ui.runOnIdle{model.refresh()};idle()
        fun enter(){
            ui.runOnIdle{model.selectSpace(model.ui.value.spaces.first{it.optString("subject_id")==subject})};idle()
        }
        fun denied(){
            val saved=checkNotNull(SavedSession(ui.activity).load())
            val connection=java.net.URI(url+"/api/v1/workbench/subjects/$subject/stories/$episode/audio").toURL().openConnection() as java.net.HttpURLConnection
            try{
                connection.setRequestProperty("Authorization","Bearer "+saved.second)
                connection.connectTimeout=15_000;connection.readTimeout=15_000
                assertEquals(404,connection.responseCode)
            }finally{connection.disconnect()}
        }
        val result=JSONObject().put("phase",phase).put("server",url).put("two_independent_devices",true).put("physical_device",false)
        when(phase){
            "create"->{
                enter();tab("我的");toggle("share-episode-$episode");click("预览分享范围");idle()
                toggle("share-audio-confirmation");toggle("share-cloud-confirmation");click("生成一次性邀请");idle()
                val invite=checkNotNull(model.ui.value.issuedInvitation)
                result.put("invitation_id",invite.getString("id")).put("code",invite.getString("code"))
            }
            "claim"->{
                denied();tab("我的");ui.onNodeWithText("粘贴邀请码").performScrollTo().performTextInput(cfg.getString("code"))
                click("领取邀请");idle();denied();result.put("not_authorized_on_claim",true)
            }
            "approve"->{
                enter();tab("我的");click("确认账号并批准");click("确认");idle()
                assertEquals("approved",model.ui.value.invitations.first{it.optString("id")==cfg.getString("invitation_id")}.getString("status"))
            }
            "play"->{
                enter();assertFalse(model.ui.value.owner)
                assertTrue(model.ui.value.stories.any{it.optString("episode_id")==episode})
                ui.runOnIdle{model.playSource(episode)}
                ui.waitUntil(30_000){model.ui.value.player.playing && model.ui.value.player.position>1000}
                result.put("position_ms",model.ui.value.player.position)
            }
            "revoke"->{
                enter();ui.runOnIdle{model.mutation("/invitations/"+cfg.getString("invitation_id")+"/revoke","POST")};idle()
            }
            "verify_revoked"->{
                denied();assertFalse(model.ui.value.player.playing)
                assertTrue(model.ui.value.stories.none{it.optString("episode_id")==episode})
                result.put("audio_denied",true).put("stale_story_removed",true)
            }
            else->error("Unknown phase")
        }
        val dir=checkNotNull(ui.activity.getExternalFilesDir(null))
        val screenshot=InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        File(dir,"paired-device.png").outputStream().use{screenshot.compress(Bitmap.CompressFormat.PNG,100,it)};screenshot.recycle()
        File(dir,"paired-device-result.json").writeText(result.toString(2))
    }
}
