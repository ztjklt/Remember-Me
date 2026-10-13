package me.remember.app

import android.content.Intent
import android.graphics.Bitmap
import android.media.AudioTrack
import android.os.ParcelFileDescriptor
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.integration.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Public-IP WSS and actual emulator AudioRecord/AudioTrack. Injected audio is
 * explicitly synthetic; this does not certify a physical microphone or AEC. */
class ContinuousVoiceLiveTest {
    @get:Rule val ui=createEmptyComposeRule()
    @Test fun continuousCallOverPublicHttps(){
        val inst=InstrumentationRegistry.getInstrumentation()
        val context=inst.targetContext
        val config=JSONObject(ParcelFileDescriptor.AutoCloseInputStream(inst.uiAutomation
            .executeShellCommand("cat /data/local/tmp/remember-voice-test.json")).bufferedReader().use{it.readText()})
        assertTrue(config.getBoolean("execute_authorized"));assertEquals("internal",BuildConfig.BUILD_TYPE)
        val folder=File(context.getExternalFilesDir(null),"continuous-voice").apply{mkdirs()}
        fun shot(name:String){val bitmap=inst.uiAutomation.takeScreenshot();File(folder,"$name.png").outputStream().use{bitmap.compress(Bitmap.CompressFormat.PNG,100,it)};bitmap.recycle()}
        fun click(text:String){
            val node=ui.onAllNodes(hasText(text) and hasClickAction()).onFirst()
            if(!node.isDisplayed())node.performScrollTo()
            node.performClick();ui.waitForIdle()
        }
        val report=JSONObject().put("physical_phone",false).put("synthetic_microphone_injection",true)
            .put("server",BuildConfig.SERVICE_URL).put("version",BuildConfig.VERSION_NAME)
        val scenario=ActivityScenario.launch<MainActivity>(Intent(context,MainActivity::class.java))
        lateinit var model:NativeWorkbenchModel
        try{
            scenario.onActivity{model=ViewModelProvider(it)[NativeWorkbenchModel::class.java]}
            ui.waitUntil(90000){!model.ui.value.busy}
            ui.runOnIdle{if(model.ui.value.actor.isNotBlank())model.logout()}
            ui.waitUntil(30000){model.ui.value.actor.isBlank()}
            ui.onNodeWithText("账号").performTextReplacement(config.getString("username"))
            ui.onNodeWithText("密码（至少8个字符）").performTextReplacement(config.getString("password"))
            click("登录");ui.waitUntil(90000){!model.ui.value.busy&&model.ui.value.actor.isNotBlank()}
            val space=model.ui.value.spaces.single{it.text("subject_id")==config.getString("subject_id")}
            if(model.ui.value.subject!=space.text("subject_id"))ui.runOnIdle{model.selectSpace(space)}
            ui.waitUntil(90000){!model.ui.value.busy&&!model.ui.value.spaceChoiceRequired}
            inst.uiAutomation.executeShellCommand("pm grant ${context.packageName} android.permission.RECORD_AUDIO").close()
            click("对话");click("语音聊聊");click("开始")
            ui.waitUntil(90000){model.voiceCall.value?.ui?.value?.ready==true||model.ui.value.error!=null}
            assertNull(model.ui.value.error)
            val engine=checkNotNull(model.voiceCall.value)
            assertTrue(engine.ui.value.ready);shot("01-listening")
            File(folder,"ready").writeText("inject synthetic question now")
            ui.waitUntil(150000){engine.ui.value.answer.isNotBlank()||engine.ui.value.error.isNotBlank()}
            assertEquals("",engine.ui.value.error)
            report.put("recognized",engine.ui.value.transcript).put("answer",engine.ui.value.answer)
            val trackField=engine.javaClass.getDeclaredField("track").apply{isAccessible=true}
            ui.waitUntil(30000){runCatching{(trackField.get(engine) as? AudioTrack)?.playbackHeadPosition?:0}.getOrDefault(0)>0}
            report.put("audio_track_advanced",true)
            click("字幕");shot("02-response")
            val oldTrack=trackField.get(engine) as AudioTrack
            File(folder,"interrupt-ready").writeText("inject second question during playback")
            ui.waitUntil(150000){engine.ui.value.transcript.contains("女儿")&&engine.ui.value.answer.contains("陈岚")||engine.ui.value.error.isNotBlank()}
            assertEquals("",engine.ui.value.error)
            assertTrue(runCatching{oldTrack.playState!=AudioTrack.PLAYSTATE_PLAYING}.getOrDefault(true))
            report.put("interrupted_answer",engine.ui.value.answer).put("old_track_stopped",true)
            shot("03-interrupted-response")
            click("暂停");ui.waitUntil(10000){engine.ui.value.paused};shot("03-paused")
            click("继续");ui.waitUntil(15000){!engine.ui.value.paused}
            scenario.moveToState(Lifecycle.State.CREATED)
            ui.waitUntil(10000){engine.ui.value.paused}
            scenario.moveToState(Lifecycle.State.RESUMED);ui.waitForIdle()
            assertTrue(engine.ui.value.paused)
            report.put("background_remains_paused",true);shot("04-return-paused")
            click("结束");ui.waitUntil(10000){model.voiceCall.value==null}
            report.put("ended",true).put("ok",true)
        }catch(error:Throwable){
            report.put("ok",false).put("failure_type",error.javaClass.simpleName)
            shot("failure");throw error
        }finally{File(folder,"result.json").writeText(report.toString(2));scenario.close()}
    }
}
