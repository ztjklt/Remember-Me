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
import org.junit.Assume.assumeFalse
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Exact non-debug APK and IP TLS smoke only. No ASR/model calls or new capture. */
class InternalStartupLiveTest {
    @get:Rule val ui=createAndroidComposeRule<MainActivity>()
    private val model get()=ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
    private fun click(text:String){
        ui.waitUntil(30_000){ui.onAllNodes(hasText(text) and isEnabled()).fetchSemanticsNodes().isNotEmpty()}
        val n=ui.onAllNodes(hasText(text) and isEnabled()).onFirst()
        if(!n.isDisplayed())n.performScrollTo()
        n.performClick()
    }
    @Test fun ordinaryLoginAndOriginalOverVerifiedIpHttps(){
        assumeFalse(BuildConfig.DEBUG)
        val automation=InstrumentationRegistry.getInstrumentation().uiAutomation
        val cfg=JSONObject(ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand("cat /data/local/tmp/remember-internal-login.json")).bufferedReader().use { it.readText() })
        ui.waitUntil(45_000){!model.ui.value.busy}
        if(model.ui.value.actor.isNotBlank()){click("我的");click("退出身份")}
        ui.onNodeWithText("连接设置 / 开发身份").assertDoesNotExist()
        ui.onNodeWithText("账号").performTextInput(cfg.getString("username"))
        ui.onNodeWithText("密码（至少10个字符）").performTextInput(cfg.getString("password"))
        click("登录")
        ui.waitUntil(60_000){model.ui.value.actor.isNotBlank() && !model.ui.value.busy || model.ui.value.error!=null}
        assertNull(model.ui.value.error);assertTrue(model.ui.value.actor.isNotBlank())
        assertEquals("https://39.108.183.47",SavedSession(ui.activity).load()?.first)
        assertEquals("paraformer-v2",model.ui.value.asrCapabilities?.optString("stt_model"))
        assertTrue(model.ui.value.stories.any {it.optString("episode_id")==cfg.getString("episode")})
        ui.runOnIdle {model.playSource(cfg.getString("episode"))}
        ui.waitUntil(30_000){model.ui.value.player.playing && model.ui.value.player.position>1000}
        ui.runOnIdle {model.seekSource(2000);model.pauseSource()}
        assertFalse(model.ui.value.player.playing)
        ui.waitForIdle()
        val out=checkNotNull(ui.activity.getExternalFilesDir(null))
        val shot=automation.takeScreenshot();File(out,"internal-ip-playback.png").outputStream().use {shot.compress(Bitmap.CompressFormat.PNG,100,it)};shot.recycle()
        File(out,"internal-ip-result.json").writeText(JSONObject().put("server","https://39.108.183.47").put("tls_validation",true)
            .put("ordinary_login",true).put("source_playback",true).put("pause_seek",true).put("debuggable",BuildConfig.DEBUG)
            .put("new_asr",false).put("new_model_call",false).put("physical_phone",false).toString(2))
        click("我的");click("退出身份")
        ui.waitUntil(15_000){model.ui.value.actor.isBlank()}
        assertTrue(model.ui.value.stories.isEmpty())
    }
}
