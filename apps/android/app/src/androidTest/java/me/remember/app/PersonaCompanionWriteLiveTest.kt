package me.remember.app

import android.content.Intent
import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.integration.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.security.MessageDigest

/** Explicitly authorized local acceptance. Uses real accounts, WAV, ASR and persisted records.
 * File import and question submission use the production model; all contribution mutations
 * are Compose control actions. No microphone simulation, fixture responses or provider retries.
 */
class PersonaCompanionWriteLiveTest {
    @get:Rule val ui=createEmptyComposeRule()
    private val instrumentation get()=InstrumentationRegistry.getInstrumentation()
    private lateinit var activity: MainActivity
    private lateinit var model: NativeWorkbenchModel
    private lateinit var folder: File
    private val result=JSONObject().put("fixture",false).put("microphone_simulated",false)
        .put("server","http://10.0.2.2:8891").put("events",JSONArray())
    private fun persist(){File(folder,"result.json").writeText(result.toString(2))}
    private fun event(name:String,data:Any=JSONObject()) {
        result.getJSONArray("events").put(JSONObject().put("name",name).put("at",java.time.Instant.now()).put("data",data));persist()
    }
    private fun idle(checkError:Boolean=true){
        ui.waitUntil(180_000){!model.ui.value.busy};ui.waitForIdle()
        if(checkError)assertNull(model.ui.value.error)
    }
    private fun action(name:String,checkError:Boolean=true,run:()->Unit){
        event("$name.started")
        ui.waitUntil(90_000){var started=false;ui.runOnIdle{if(!model.ui.value.busy){run();started=true}};started}
        idle(checkError);event("$name.finished",JSONObject().put("error",model.ui.value.error?:JSONObject.NULL))
    }
    private fun click(label:String,within:String?=null){
        val matcher=hasText(label) and hasClickAction() and (within?.let{hasAnyAncestor(hasTestTag(it))}?:SemanticsMatcher("any"){true})
        ui.waitUntil(30_000){ui.onAllNodes(matcher).fetchSemanticsNodes().isNotEmpty()}
        val node=ui.onAllNodes(matcher).onFirst()
        if(!node.isDisplayed())node.performScrollTo()
        node.assertIsEnabled().performClick();idle()
    }
    private fun toggle(tag:String){
        val node=ui.onNodeWithTag(tag);node.performScrollTo();node.assertIsOff();node.performClick();idle()
    }
    private fun shot(name:String){
        ui.waitForIdle();Thread.sleep(500);ui.waitForIdle()
        val bitmap=instrumentation.uiAutomation.takeScreenshot()
        File(folder,"$name.png").outputStream().use{bitmap.compress(Bitmap.CompressFormat.PNG,100,it)};bitmap.recycle()
    }
    private fun note(id:String)=model.ui.value.companion.rows("contributions").first{it.text("id")==id}
    private fun showNote(id:String){ui.onNodeWithTag("contribution-$id").performScrollTo();ui.waitForIdle()}

    @Test fun authorizedLocalContributionPhase(){
        val context=instrumentation.targetContext
        val secret=File(context.filesDir,"persona-write-login.json")
        val config=JSONObject(secret.readText());secret.delete()
        assertTrue("Explicit local write authorization required",config.getBoolean("execute_authorized"))
        val phase=config.getString("phase")
        val role=if(phase.startsWith("owner")) "owner" else "reader"
        folder=File(context.getExternalFilesDir(null),"persona-write/$phase").apply{mkdirs()}
        result.put("phase",phase).put("role",role).put("interaction_method","Compose controls; real-file import and question via production NativeWorkbenchModel")
        persist()
        val login=accountRequest("http://10.0.2.2:8891","login",JSONObject().put("username",config.getString("username")).put("password",config.getString("password")))
        SavedSession(context).save("http://10.0.2.2:8891",login.getString("actor_token"))
        val scenario=ActivityScenario.launch<MainActivity>(Intent(context,MainActivity::class.java))
        try {
            scenario.onActivity{activity=it;model=ViewModelProvider(it)[NativeWorkbenchModel::class.java]}
            idle();ui.waitUntil(60_000){model.ui.value.actor.isNotBlank()};idle()
            assertEquals(1f,activity.resources.configuration.fontScale)
            val subject=config.getString("subject_id")
            if(model.ui.value.subject!=subject){
                if(model.ui.value.spaceChoiceRequired)ui.onNodeWithTag("choose-space-$subject").performClick()
                else{ui.onNodeWithTag("space-chooser").performClick();ui.onNodeWithTag("space-$subject").performClick()};idle()
            }
            assertEquals(role=="owner",model.ui.value.owner)
            result.put("actor_id",model.ui.value.actor).put("subject_id",model.ui.value.subject).put("font_scale",1f)
            if(activity.getSharedPreferences("remember-appearance",0).getBoolean("simple_mode",false)){click("我的");click("简明模式")}
            click("档案");click("亲友");idle()
            when(phase){
                "reader-create" -> {
                    assertNull("Preserve any existing unsent audio draft",model.ui.value.companionAudio)
                    assertTrue(model.ui.value.companion.rows("contribution_grants").any{it.text("actor_id")==model.ui.value.actor&&it.optBoolean("enabled")})
                    val wav=File(context.filesDir,"persona-write-source.wav")
                    val sha=MessageDigest.getInstance("SHA-256").digest(wav.readBytes()).joinToString(""){"%02x".format(it)}
                    assertEquals(config.getString("wav_sha256"),sha);result.put("wav_sha256",sha).put("wav_bytes",wav.length())
                    action("import.real_wav"){model.importCompanionAudio("contribution","audio/wav"){wav.readBytes()}}
                    shot("01-real-file-imported")
                    event("upload.started");click("上传这段声音")
                    val uploaded=model.ui.value.companionAudio!!.remote!!
                    result.put("audio_id",uploaded.text("audio_id"));event("upload.finished",uploaded);shot("02-audio-saved")
                    toggle("contribution-cloud-asr");event("asr.started");click("转为文字")
                    val transcribed=model.ui.value.companionAudio!!.remote!!
                    val transcript=transcribed.text("transcript_text")
                    event("asr.finished",transcribed);assertTrue(transcript.length>30)
                    ui.onNodeWithText("核对录音文字").performScrollTo();shot("03-real-asr-review")
                    event("review.started");click("确认录音文字")
                    val reviewed=model.ui.value.companionAudio!!.remote!!
                    assertEquals("confirmed",reviewed.text("status"));assertEquals(transcript,reviewed.text("reviewed_text"))
                    result.put("review_method","Automated acceptance of the actual returned transcript, unchanged; no typed replacement or human listening claim")
                    event("review.finished",reviewed)
                    click("把已核对文字填入正文");ui.onNodeWithTag("contribution-text").performScrollTo();shot("04-reviewed-text-in-form")
                    event("submit.started");click("署名提交，等待审核")
                    val created=model.ui.value.companion.rows("contributions").single{it.text("audio_id")==uploaded.text("audio_id")}
                    val id=created.text("id");result.put("note_id",id);event("submit.finished",created)
                    assertEquals("pending",created.text("status"));assertFalse(contributionModelUseAllowed(created))
                    showNote(id);shot("05-submitted-pending")
                    ui.onNodeWithTag("contribution-model-use-$id").assertIsNotEnabled()
                }
                "owner-accept" -> {
                    val id=config.getString("note_id");result.put("note_id",id)
                    assertEquals("pending",note(id).text("status"));assertFalse(note(id).optBoolean("model_use_author_allowed"))
                    ui.onNodeWithTag("contribution-model-use-$id").assertIsNotEnabled()
                    showNote(id);shot("07-owner-pending")
                    event("owner_accept.started");click("接受","contribution-$id")
                    assertEquals("accepted",note(id).text("status"));event("owner_accept.finished",note(id))
                    event("owner_model_use.started");toggle("contribution-model-use-$id")
                    assertTrue(note(id).optBoolean("model_use_owner_allowed"));assertFalse(note(id).optBoolean("model_use_author_allowed"))
                    event("owner_model_use.finished",note(id));showNote(id);shot("08-owner-opt-in")
                }
                "reader-opt-in" -> {
                    val id=config.getString("note_id");result.put("note_id",id)
                    assertEquals("accepted",note(id).text("status"));assertTrue(note(id).optBoolean("model_use_owner_allowed"))
                    event("author_model_use.started");toggle("contribution-model-use-$id")
                    assertTrue(contributionModelUseAllowed(note(id)));event("author_model_use.finished",note(id));showNote(id);shot("08b-both-opt-in")
                }
                "reader-question" -> {
                    val id=config.getString("note_id");result.put("note_id",id);assertTrue(contributionModelUseAllowed(note(id)))
                    click("对话")
                    val question="亲友这次署名补记的原话是什么？请区分这是谁的记录。"
                    result.put("question",question).put("mode","persona").put("original_compound_issue_retested",false)
                    action("question.once",false){model.ask(question,true,"persona")}
                    val answer=model.ui.value.answer
                    result.put("question_error",model.ui.value.error?:JSONObject.NULL).put("answer",answer?:JSONObject.NULL)
                    if(answer!=null){ui.onNodeWithText(answer.text("answer")).performScrollTo();shot("09-persona-original-quote-answer")}
                    else shot("09-persona-question-failure")
                    persist()
                }
                "reader-withdraw" -> {
                    val id=config.getString("note_id");result.put("note_id",id)
                    assertEquals(model.ui.value.actor,note(id).text("author_actor_id"))
                    event("author_withdraw.started");click("撤回补记","contribution-$id");shot("10-withdraw-confirmation");click("确认")
                    assertEquals("withdrawn",note(id).text("status"));event("author_withdraw.finished",note(id));showNote(id);shot("11-author-withdrawn")
                }
                "owner-verify" -> {
                    val id=config.getString("note_id");result.put("note_id",id)
                    val withdrawn=note(id);assertEquals("withdrawn",withdrawn.text("status"));assertTrue(withdrawn.text("text").isBlank());assertTrue(withdrawn.text("audio_id").isBlank())
                    event("withdrawn.owner_view",withdrawn);showNote(id);shot("12-owner-withdrawn-no-content")
                }
                else -> error("Unknown explicit acceptance phase")
            }
            result.put("completed",true);persist()
        }catch(e:Throwable){result.put("completed",false).put("failure",e.message);persist();if(::activity.isInitialized)runCatching{shot("failure")};throw e}
        finally{scenario.close()}
    }
}
