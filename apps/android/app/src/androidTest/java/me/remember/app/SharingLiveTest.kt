package me.remember.app

import android.graphics.Bitmap
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

/** Real HTTP/ordinary account journey on an explicit isolated corpus copy.
 * One emulator switching accounts plus a separate reader HTTP session;
 * this does not claim a physical phone or a new ASR/model run.
 */
class SharingLiveTest {
    @get:Rule val ui=createAndroidComposeRule<MainActivity>()
    private val model get()=ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
    private val outputDir get()=if(BuildConfig.DEBUG) ui.activity.filesDir else checkNotNull(ui.activity.getExternalFilesDir(null))
    private fun idle(){ ui.waitUntil(60_000){!model.ui.value.busy};assertNull(model.ui.value.error) }
    private fun click(text:String){
        ui.waitUntil(30_000){ui.onAllNodes(hasText(text) and isEnabled()).fetchSemanticsNodes().isNotEmpty()}
        val node=ui.onAllNodes(hasText(text) and isEnabled()).onFirst()
        if(!node.isDisplayed())node.performScrollTo()
        node.performClick()
    }
    private fun tab(text:String){
        // Model completion can precede the following Compose frame.
        ui.waitUntil(30_000){ui.onAllNodesWithText(text,useUnmergedTree=true).fetchSemanticsNodes().isNotEmpty()}
        ui.onNodeWithText(text,useUnmergedTree=true).performClick()
    }
    private fun toggle(text:String){
        val selector=hasTestTag(text) and isEnabled()
        try { ui.waitUntil(30_000){ui.onAllNodes(selector).fetchSemanticsNodes().isNotEmpty()} }
        catch(error:Throwable){
            shot("toggle-failure")
            File(ui.activity.filesDir,"paired-ui-tree.txt").writeText(ui.onRoot(useUnmergedTree=true).printToString())
            File(ui.activity.filesDir,"paired-ui-failure.txt").writeText("error=${model.ui.value.error}; busy=${model.ui.value.busy}; preview=${model.ui.value.sharePreview!=null}; target=$text")
            throw error
        }
        ui.onAllNodes(selector).onFirst().performScrollTo().performClick()
    }
    private fun shot(name:String){
        val image=InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        File(outputDir,"paired-$name.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG,100,it) };image.recycle()
    }
    @Test fun ordinaryAccountsClaimApproveListenReshareRevoke(){
        val file=File(ui.activity.filesDir,"sharing-ui.json")
        val configText=if(file.exists()) file.readText() else {
            // Explicit test-only shell fixture; no passwords in instrumentation arguments.
            val fd=InstrumentationRegistry.getInstrumentation().uiAutomation.executeShellCommand("cat /data/local/tmp/remember-paired-config.json")
            android.os.ParcelFileDescriptor.AutoCloseInputStream(fd).bufferedReader().use { it.readText() }
        }
        assumeTrue(configText.trim().startsWith("{"))
        val cfg=JSONObject(configText);val url=cfg.getString("url");val subject=cfg.getString("subject");val episode=cfg.getString("episode")
        fun assertSourceDenied(){
            val saved=checkNotNull(SavedSession(ui.activity).load())
            val connection=java.net.URI(url+"/api/v1/workbench/subjects/$subject/stories/$episode/audio").toURL().openConnection() as java.net.HttpURLConnection
            try { connection.setRequestProperty("Authorization","Bearer "+saved.second);connection.connectTimeout=15_000;connection.readTimeout=15_000
                assertEquals(404,connection.responseCode)
            } finally {connection.disconnect()}
        }
        fun login(person:JSONObject){
            idle()
            if(model.ui.value.actor.isNotBlank()){tab("我的");click("退出身份");idle()}
            if(url!=BuildConfig.SERVICE_URL){click("连接设置 / 开发身份");ui.onNodeWithText("共享后端地址").performScrollTo().performTextReplacement(url)}
            ui.onNodeWithText("账号").performScrollTo().performTextReplacement(person.getString("username"))
            ui.onNodeWithText("密码（至少10个字符）").performScrollTo().performTextInput(person.getString("password"))
            click("登录")
            ui.waitUntil(60_000){model.ui.value.actor==person.getString("actor_id") && !model.ui.value.busy || model.ui.value.error!=null}
            idle();assertEquals(person.getString("actor_id"),model.ui.value.actor)
        }
        val reader=cfg.getJSONObject("reader");val owner=cfg.getJSONObject("owner")
        login(owner)
        val ownSpace=model.ui.value.spaces.first { it.optString("subject_id")==subject }
        ui.runOnIdle { model.selectSpace(ownSpace) };idle();tab("我的")
        // Only clean previous failed attempts for this explicitly isolated test pair.
        for(grant in model.ui.value.grants.filter { it.optString("episode_id")==episode && it.optString("reader_actor_id")==reader.getString("actor_id") }) {
            ui.runOnIdle { model.mutation("/grants/${grant.getString("grant_id")}","DELETE") };idle()
        }
        toggle("share-episode-$episode");click("预览分享范围");idle()
        toggle("share-audio-confirmation");toggle("share-cloud-confirmation")
        click("生成一次性邀请");idle()
        val invitation=checkNotNull(model.ui.value.issuedInvitation)
        val id=invitation.getString("id");val code=invitation.getString("code");shot("invitation")
        login(reader);assertSourceDenied()
        tab("我的");ui.onNodeWithText("粘贴邀请码").performScrollTo().performTextInput(code);click("领取邀请");idle()
        assertSourceDenied();shot("waiting-owner")
        login(owner);ui.runOnIdle { model.selectSpace(model.ui.value.spaces.first { it.optString("subject_id")==subject }) };idle();tab("我的")
        click("确认账号并批准");click("确认");idle()
        assertEquals("approved",model.ui.value.invitations.first { it.optString("id")==id }.getString("status"))
        // A genuinely separate login survives logout of the owner's phone session.
        val secondary=accountRequest(url,"login",JSONObject().put("username",owner.getString("username")).put("password",owner.getString("password")))
        val ownerGate=SessionGate();val os=ownerGate.connect(url,secondary.getString("actor_token"));val ownerClient=BackendClient(ownerGate)
        login(reader)
        ui.runOnIdle { model.selectSpace(model.ui.value.spaces.first { it.optString("subject_id")==subject }) };idle()
        assertFalse(model.ui.value.owner);assertTrue(model.ui.value.stories.any { it.optString("episode_id")==episode })
        ui.runOnIdle { model.playSource(episode) };ui.waitUntil(30_000){model.ui.value.player.playing};shot("reader-audio")
        ownerClient.json(os,"/api/v1/workbench/subjects/$subject/invitations/$id/revoke","POST")
        ui.runOnIdle { model.refresh() };idle()
        assertFalse(model.ui.value.player.playing)
        assertSourceDenied()
        assertTrue(model.ui.value.stories.none { it.optString("episode_id")==episode });shot("revoked")
        login(owner);ui.runOnIdle { model.selectSpace(model.ui.value.spaces.first { it.optString("subject_id")==subject }) };idle()
        assertTrue(model.ui.value.recipients.any { it.optString("username")==reader.getString("username") })
        tab("我的");click("退出身份");idle();assertTrue(model.ui.value.stories.isEmpty());assertTrue(model.ui.value.invitations.isEmpty())
        File(outputDir,"paired-sharing-result.json").writeText(JSONObject().put("claim_requires_approval",true).put("playback",true).put("revocation",true)
            .put("ordinary_account_switch",true).put("fresh_asr",false).put("two_emulators",false).put("physical_device",false).toString(2))
    }
}
