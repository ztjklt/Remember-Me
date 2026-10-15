package me.remember.app

import android.content.Intent
import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.data.repository.AudioRecording
import me.remember.app.integration.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.time.Instant

/** Opt-in public HTTPS acceptance. A prerecorded synthetic file replaces only
 * microphone capture; app upload, cloud ASR/correction and review are real. */
class CloudProofreadingLiveTest {
    @get:Rule val ui=createEmptyComposeRule()
    @Test fun proofreadingAndRevisionOverPublicHttps() {
        val inst=InstrumentationRegistry.getInstrumentation();val context=inst.targetContext
        fun shellBytes(command:String)=ParcelFileDescriptor.AutoCloseInputStream(inst.uiAutomation.executeShellCommand(command)).use{it.readBytes()}
        val config=JSONObject(String(shellBytes("cat /data/local/tmp/remember-proofreading-test.json")))
        assertTrue(config.getBoolean("execute_authorized"));assertEquals("https://39.108.183.47",BuildConfig.SERVICE_URL)
        val folder=File(context.getExternalFilesDir(null),"cloud-proofreading").apply{mkdirs()}
        val report=JSONObject().put("physical_phone",false).put("prerecorded_synthetic_input",true).put("version",BuildConfig.VERSION_NAME)
        fun shot(name:String){ui.waitForIdle();Thread.sleep(600);val b=inst.uiAutomation.takeScreenshot();File(folder,"$name.png").outputStream().use{b.compress(Bitmap.CompressFormat.PNG,100,it)};b.recycle()}
        fun click(text:String){val n=ui.onAllNodes(hasText(text) and hasClickAction()).onFirst();if(!n.isDisplayed())n.performScrollTo();n.performClick();ui.waitForIdle()}
        val scenario=ActivityScenario.launch<MainActivity>(Intent(context,MainActivity::class.java))
        lateinit var model:NativeWorkbenchModel
        fun idle(){ui.waitUntil(120000){!model.ui.value.busy};assertNull(model.ui.value.error)}
        fun act(block:()->Unit){ui.waitUntil(120000){!model.ui.value.busy};ui.runOnIdle(block);idle()}
        try {
            scenario.onActivity{model=ViewModelProvider(it)[NativeWorkbenchModel::class.java]}
            ui.waitUntil(90000){!model.ui.value.busy}
            if(model.ui.value.actor.isNotBlank())act{model.logout()}
            ui.onNodeWithText("账号").performTextReplacement(config.getString("username"))
            ui.onNodeWithText("密码（至少8个字符）").performTextReplacement(config.getString("password"));click("登录")
            ui.waitUntil(90000){model.ui.value.actor.isNotBlank()&&!model.ui.value.busy};idle()
            assertTrue(model.ui.value.owner)
            val source=File(context.filesDir,"cloud-proofreading-synthetic.wav");source.writeBytes(shellBytes("cat /data/local/tmp/remember-proofreading-sample.wav"))
            val capture=model.ui.value.local.firstOrNull{it.key==config.getString("run_id")} ?: LocalCapture(AudioRecording(source.path,42000,"audio/wav",source.length(),24000,1,Instant.now().toString()),config.getString("run_id"),source="IMPORT")
            if(capture.episode.isBlank())act{model.upload(capture,true)}
            val ep=model.ui.value.local.single{it.key==capture.key}.episode
            assertTrue(ep.isNotBlank());report.put("episode_id",ep).put("subject_id",model.ui.value.subject)
            ui.waitUntil(180000){model.ui.value.stories.any{it.text("episode_id")==ep&&it.optBoolean("waiting_for_review")}}
            assertTrue(model.ui.value.stories.single{it.text("episode_id")==ep}.rows("memories").isEmpty())
            act{model.review(ep)}
            val raw=model.ui.value.reviewMachineText;val draft=model.ui.value.reviewInitialText
            assertEquals("completed",model.ui.value.reviewCorrection?.text("status"));assertTrue(raw.isNotBlank());assertTrue(draft.isNotBlank())
            report.put("machine_transcript",raw).put("automatic_draft",draft).put("correction",model.ui.value.reviewCorrection)
            shot("01-automatic-draft")
            if(model.ui.value.reviewCorrection!!.rows("edits").isNotEmpty()){
                click("查看修改");shot("02-correction-details");click("恢复机器稿");assertEquals(raw,model.ui.value.reviewText)
                click("恢复自动修订稿");assertEquals(draft,model.ui.value.reviewText)
                click("收起修改")
            }
            // Resolve the deliberately preserved uncertain homophone after listening
            // to the fictional fixture; this is test-author review, not model output.
            val checked=draft.replace("该谢就谢","该歇就歇")
            ui.onNodeWithText("核对后的文字").performScrollTo().performTextReplacement(checked)
            ui.onNode(hasText("我确认文字与补充说明，并同意交由云端模型整理和用于之后的问答。") and isToggleable()).performScrollTo().performClick()
            shot("03-confirm-text");click("确认文字并整理");idle()
            ui.waitUntil(180000){model.ui.value.stories.any{it.text("episode_id")==ep&&it.text("status") in listOf("ready","failed")}}
            var story=model.ui.value.stories.single{it.text("episode_id")==ep};assertEquals("ready",story.text("status"));assertEquals(raw,story.text("machine_transcript"));assertTrue(story.rows("memories").isNotEmpty())
            report.put("story",story).put("no_memories_before_confirmation",true)
            click("档案");click("全部录音");shot("04-organized-recording")
            act{model.playSource(ep)};ui.waitUntil(30000){model.ui.value.player.playing&&model.ui.value.player.position>=1000};shot("05-original-playing");act{model.stopSource()}
            val memory=story.rows("memories").first{it.text("content").contains("杯")}
            val revised="蓝色搪瓷杯现在留作纪念，不是现在每天喝茶用的杯子。"
            report.put("previous_memory",memory).put("owner_test_correction",revised)
            // Existing app mutation/API seam. The new-recording revision entry is
            // separate; do not claim this is a visible text-edit button.
            act{model.mutation("/memories/${segment(memory.text("memory_item_id"))}","PATCH",JSONObject().put("content",revised),true)}
            story=model.ui.value.stories.single{it.text("episode_id")==ep};assertEquals(revised,story.rows("memories").single{it.text("memory_item_id")==memory.text("memory_item_id")}.text("content"))
            click("对话");act{model.ask("蓝色搪瓷杯现在是每天喝茶用的吗？",true)}
            val answer=checkNotNull(model.ui.value.answer);assertFalse(answer.optBoolean("stale",true));assertTrue(answer.rows("evidence").any{it.text("excerpt").contains("留作纪念")})
            report.put("answer_after_revision",answer);shot("06-answer-after-correction");report.put("ok",true)
        } finally {File(folder,"result.json").writeText(report.toString(2));scenario.close()}
    }
}
