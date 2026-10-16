package me.remember.app

import android.content.Intent
import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.integration.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Local backend only. Login and reading; no questions, grants, content or provider calls. */
class PersonaReadOnlyLiveTest {
    @get:Rule val ui=createEmptyComposeRule()
    private val instrumentation get()=InstrumentationRegistry.getInstrumentation()
    private lateinit var activity: MainActivity
    private lateinit var model: NativeWorkbenchModel
    private var role="owner"
    private var captureFolder="persona-readonly"
    private fun idle(){ui.waitUntil(90_000){!model.ui.value.busy};assertNull(model.ui.value.error)}
    private fun readAction(action: () -> Unit) {
        ui.waitUntil(90_000) {
            var started=false
            ui.runOnIdle {if(!model.ui.value.busy){action();started=true}}
            started
        }
        idle();ui.waitForIdle()
    }
    private fun revealComparison(node: SemanticsNodeInteraction) {
        node.performScrollTo();ui.waitForIdle()
        val viewport=ui.onNode(SemanticsMatcher.keyIsDefined(SemanticsProperties.VerticalScrollAxisRange))
        val delta=node.fetchSemanticsNode().boundsInRoot.top-viewport.fetchSemanticsNode().boundsInRoot.top
        if(delta>0)viewport.performSemanticsAction(SemanticsActions.ScrollBy){it(0f,delta)}
        ui.waitForIdle()
    }
    private fun click(label: String){
        ui.waitUntil(30_000){ui.onAllNodes(hasText(label) and hasClickAction()).fetchSemanticsNodes().isNotEmpty()}
        val node=ui.onAllNodes(hasText(label) and hasClickAction()).onFirst()
        if(!node.isDisplayed())node.performScrollTo()
        ui.waitUntil(30_000){ui.onAllNodes(hasText(label) and hasClickAction() and isEnabled()).fetchSemanticsNodes().isNotEmpty()}
        ui.onAllNodes(hasText(label) and hasClickAction()).onFirst().performClick();ui.waitForIdle()
    }
    private fun shot(name: String){
        idle();ui.waitForIdle();Thread.sleep(500);ui.waitForIdle()
        val folder=File(activity.getExternalFilesDir(null),"$captureFolder/$role").apply{mkdirs()}
        val bitmap=instrumentation.uiAutomation.takeScreenshot()
        File(folder,"$name.png").outputStream().use{bitmap.compress(Bitmap.CompressFormat.PNG,100,it)};bitmap.recycle()
    }
    @Test fun currentLocalOwnerPagesAtNormalTextSize(){
        val context=instrumentation.targetContext
        val secret=File(context.filesDir,"persona-live-login.json")
        val config=JSONObject(secret.readText());secret.delete();role=config.optString("role","owner")
        captureFolder=config.optString("capture_folder","persona-readonly")
        require(captureFolder.matches(Regex("[a-z0-9-]+")))
        var originalRead: JSONObject?=null
        val login=accountRequest("http://10.0.2.2:8891","login",JSONObject().put("username",config.getString("username")).put("password",config.getString("password")))
        SavedSession(context).save("http://10.0.2.2:8891",login.getString("actor_token"))
        val scenario=ActivityScenario.launch<MainActivity>(Intent(context,MainActivity::class.java))
        try {
            scenario.onActivity{activity=it;model=ViewModelProvider(it)[NativeWorkbenchModel::class.java]}
            idle();assertEquals(1f,activity.resources.configuration.fontScale)
            ui.waitUntil(60_000){model.ui.value.actor.isNotBlank()};idle()
            val target=model.ui.value.spaces.first{it.text("display_name").contains("陈国梁")}
            if(model.ui.value.subject!=target.text("subject_id")){
                if(model.ui.value.spaceChoiceRequired)ui.onNodeWithTag("choose-space-${target.text("subject_id")}").performClick()
                else{ui.onNodeWithTag("space-chooser").performClick();ui.onNodeWithTag("space-${target.text("subject_id")}").performClick()};idle()
            }
            assertEquals(role=="owner",model.ui.value.owner)
            assertTrue("Confirmed understandings must meet this capture's explicit minimum",confirmedUnderstandings(model.ui.value.narrative).size>=config.optInt("minimum_understandings",0))
            if(activity.getSharedPreferences("remember-appearance",0).getBoolean("simple_mode",false)){click("我的");click("简明模式")}
            click("档案");click("花田");idle();shot("01-native-garden")
            click("人物");idle();shot("02-native-person-understanding")
            confirmedUnderstandings(model.ui.value.narrative).take(3).forEachIndexed{i,item->
                if(i>0)ui.onNodeWithContentDescription("下一条理解").performClick()
                click("查看情境与来源");shot("03-understanding-${i+1}");click("返回人物")
            }
            shot("03b-native-person-content")
            click("对话");idle();shot("04-native-persona-selector")
            ui.onNodeWithText("与 AI 分身聊聊").assertExists()
            if(config.optString("answer_id").isNotBlank()) {
                readAction{model.openSavedAnswer(config.getString("answer_id"))}
                val answer=model.ui.value.answer!!
                ui.onNodeWithText(answer.text("answer")).performScrollTo();shot("08-native-saved-persona-answer")
                if(config.optString("asset_id").isNotBlank()) {
                    readAction{model.playSavedSpeech(config.getString("answer_id"),config.getString("asset_id"))}
                    ui.waitUntil(15_000){model.ui.value.player.playing};assertTrue(model.ui.value.player.duration>0)
                    shot("09-native-saved-voice-playing");ui.runOnIdle{model.stopSource()}
                }
            }
            if(role=="owner" && config.optString("calibration_id").isNotBlank()) {
                readAction{model.openCalibration(config.getString("calibration_id"))}
                assertEquals(config.getString("calibration_id"),model.ui.value.calibrationId)
                val run=model.ui.value.calibrations.first{it.text("calibration_id")==config.getString("calibration_id")}
                assertEquals("complete",run.text("status"))
                revealComparison(ui.onNodeWithText(run.text("locked_answer")));shot("10a-native-calibration-locked-answer")
                revealComparison(ui.onNodeWithText(run.text("summary")));shot("10-native-calibration-comparison")
                assertEquals(5,run.rows("dimensions").size)
                run.rows("dimensions").forEachIndexed {index,item ->
                    revealComparison(ui.onNodeWithTag("calibration-dimension-${item.text("dimension")}"));shot("11-native-calibration-difference-${index+1}")
                }
                ui.runOnIdle{model.closeCalibration()}
            }
            if(role=="owner") {click("对话工具");click("分身声音与亲友许可");ui.onNodeWithText(if(model.ui.value.voiceProfile.optBoolean("ready")) "分身声音已就绪" else "分身声音尚未启用").performScrollTo();shot("05-native-owner-voice-controls")}
            click("档案");click("亲友");idle();shot("06-native-companion")
            if(config.optString("contribution_id").isNotBlank()) {
                val originalId=config.getString("contribution_id")
                val originalButton=ui.onNodeWithTag("contribution-original-$originalId")
                originalButton.performScrollTo();ui.waitForIdle()
                ui.waitUntil(30_000){!model.ui.value.busy}
                originalButton.assertIsEnabled().performSemanticsAction(SemanticsActions.OnClick){assertTrue(it())}
                ui.waitUntil(30_000){model.ui.value.contributionOriginal!=null||model.ui.value.error!=null};idle()
                val original=model.ui.value.contributionOriginal!!
                originalRead=original
                assertEquals(originalId,original.text("id"))
                assertTrue(original.text("author_display_name").isNotBlank())
                ui.onNode(hasText(original.text("text")) and hasAnyAncestor(isDialog())).assertIsDisplayed()
                shot("06b-native-companion-original")
                click("关闭")
            }
            click("留给你");idle();shot("07-native-dedicated-letter")
            if(config.optString("letter_audio_id").isNotBlank()) {
                readAction{model.playCompanionAudio(config.getString("letter_audio_id"))}
                ui.waitUntil(15_000){model.ui.value.player.playing};assertTrue(model.ui.value.player.duration>0)
                shot("12-native-letter-audio-playing");ui.runOnIdle{model.stopSource()}
            }
            if(config.optBoolean("leave_open")){click("档案");click("人物");shot("13-final-owner-person")}
            val result=JSONObject().put("server","http://10.0.2.2:8891").put("font_scale",activity.resources.configuration.fontScale)
                .put("confirmed_understandings",confirmedUnderstandings(model.ui.value.narrative).size).put("stories",model.ui.value.stories.size)
                .put("persona_enabled",model.ui.value.narrative.optJSONObject("style")?.optBoolean("enabled")).put("voice_ready",model.ui.value.voiceProfile.optBoolean("ready"))
                .put("role",role).put("content_mutations",0).put("questions",0).put("fixture",false)
                .put("calibration_read",config.optString("calibration_id")).put("answer_read",config.optString("answer_id"))
                .put("contribution_read",config.optString("contribution_id"))
                .put("original_model_use_author_allowed",originalRead?.optBoolean("model_use_author_allowed")?:JSONObject.NULL)
                .put("original_model_use_owner_allowed",originalRead?.optBoolean("model_use_owner_allowed")?:JSONObject.NULL)
                .put("existing_speech_played",config.optString("asset_id").isNotBlank()).put("letter_audio_played",config.optString("letter_audio_id").isNotBlank())
            File(activity.getExternalFilesDir(null),"$captureFolder/$role/result.json").writeText(result.toString(2))
        }catch(e: Throwable){if(::activity.isInitialized)shot("failure");throw e}finally{if(!config.optBoolean("leave_open"))scenario.close()}
    }
}
