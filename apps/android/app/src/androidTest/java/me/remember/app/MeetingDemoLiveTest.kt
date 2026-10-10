package me.remember.app

import android.Manifest
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

/** Explicit opt-in: real ordinary account, native recorder and real ECS calls.
 * The host supplies fictional sound to the emulator microphone, never ASR text.
 */
class MeetingDemoLiveTest {
    @get:Rule val ui=createAndroidComposeRule<MainActivity>()
    private val model get()=ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
    private val out get()=File(ui.activity.getExternalFilesDir(null),"meeting-demo").apply{mkdirs()}
    private fun idle(){ui.waitUntil(120_000){!model.ui.value.busy};assertNull(model.ui.value.error)}
    private fun click(text:String){
        val match=hasText(text) and isEnabled()
        ui.waitUntil(40_000){ui.onAllNodes(match).fetchSemanticsNodes().isNotEmpty()}
        val node=ui.onAllNodes(match).onFirst();if(!node.isDisplayed())node.performScrollTo();node.performClick()
    }
    private fun tab(text:String)=ui.onNodeWithText(text,useUnmergedTree=true).performClick()
    private fun check(text:String)=ui.onAllNodes(isToggleable() and hasAnySibling(hasText(text,substring=true))).onFirst().performScrollTo().performClick()
    private fun shot(name:String){
        ui.waitForIdle()
        // Allow the real display compositor to present the frame after scrolling.
        Thread.sleep(650)
        File(out,"$name.png").outputStream().use{stream->InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot().compress(Bitmap.CompressFormat.PNG,100,stream)}
    }
    private fun report(phase:String,extra:JSONObject=JSONObject()){
        extra.put("phase",phase).put("server",BuildConfig.SERVICE_URL).put("emulator",true).put("physical_microphone",false)
        File(out,"$phase.json").writeText(extra.toString(2))
    }
    private fun switchAccount(person:JSONObject){
        tab("我的");click("退出身份");idle()
        ui.onNodeWithText("账号").performScrollTo().performTextReplacement(person.getString("username"))
        ui.onNodeWithText("密码（至少10个字符）").performScrollTo().performTextInput(person.getString("password"))
        click("登录")
        ui.waitUntil(120_000){model.ui.value.actor==person.getString("actor_id")||model.ui.value.error!=null};idle()
    }
    private fun toggle(tag:String){ui.onNodeWithTag(tag).performScrollTo().performClick()}
    @Test fun meetingJourney(){
        val fd=InstrumentationRegistry.getInstrumentation().uiAutomation.executeShellCommand("cat /data/local/tmp/remember-meeting.json")
        val cfg=JSONObject(ParcelFileDescriptor.AutoCloseInputStream(fd).bufferedReader().use{it.readText()})
        require(BuildConfig.SERVICE_URL=="https://39.108.183.47")
        val person=cfg.getJSONObject("account")
        idle()
        if(model.ui.value.actor!=person.getString("actor_id")){
            if(model.ui.value.actor.isNotBlank()){tab("我的");click("退出身份");idle()}
            shot("01-login")
            ui.onNodeWithText("账号").performTextReplacement(person.getString("username"))
            ui.onNodeWithText("密码（至少10个字符）").performTextInput(person.getString("password"))
            click("登录")
            ui.waitUntil(120_000){model.ui.value.actor==person.getString("actor_id")||model.ui.value.error!=null};idle()
        }
        assertEquals(person.getString("actor_id"),model.ui.value.actor)
        tab("今天");shot("02-today")
        val phase=cfg.optString("phase","record")
        if(phase in setOf("share","reader")){
            val ep=File(out,"episode-id").readText().trim()
            val ownerSubject=model.ui.value.subject
            val reader=cfg.getJSONObject("reader")
            val invite:JSONObject
            if(phase=="share"){
            tab("我的");toggle("share-episode-$ep");click("预览分享范围");idle()
            ui.onNodeWithTag("share-audio-confirmation").performScrollTo();shot("22-share-preview")
            toggle("share-audio-confirmation");toggle("share-cloud-confirmation");click("生成一次性邀请");idle()
            invite=checkNotNull(model.ui.value.issuedInvitation)
            click("复制邀请码");shot("23-invitation-created")
            switchAccount(reader)
            assertTrue(model.ui.value.stories.none{it.text("episode_id")==ep})
            tab("我的");ui.onNodeWithText("粘贴邀请码").performScrollTo().performTextInput(invite.getString("code"))
            click("领取邀请");idle();shot("24-reader-claimed")
            assertTrue(model.ui.value.stories.none{it.text("episode_id")==ep})
            switchAccount(person);tab("我的");click("确认账号并批准");shot("25-owner-confirmation");click("确认");idle()
            assertEquals("approved",model.ui.value.invitations.first{it.text("id")==invite.getString("id")}.text("status"))
            } else {
                invite=model.ui.value.invitations.first{it.text("status")=="approved"&&it.rows("scope").any{scope->scope.text("episode_id")==ep}}
            }
            switchAccount(reader)
            val target=model.ui.value.spaces.first{it.text("subject_id")==ownerSubject}
            if(model.ui.value.subject!=ownerSubject){
                val current=checkNotNull(model.ui.value.space)
                click(current.text("display_name")+" · "+if(model.ui.value.owner)"记录者" else "授权读者")
                click(target.text("display_name")+" · "+target.text("role"));idle()
            }
            assertFalse(model.ui.value.owner)
            assertTrue(model.ui.value.stories.any{it.text("episode_id")==ep})
            tab("今天");shot("26-reader-stories");click("打开故事");shot("27-reader-story-detail");click("播放完整原音")
            ui.waitUntil(30_000){model.ui.value.player.playing&&model.ui.value.player.position>1000}
            shot("28-reader-playing");click("停止播放")
            tab("对话");ui.onNodeWithText("想了解什么？").performTextInput("记录者小时候最喜欢的老师叫什么名字？")
            check("同意本次将问题和有权访问");click("提问");idle()
            val answer=checkNotNull(model.ui.value.answer)
            File(out,"reader-unknown-answer.json").writeText(answer.toString(2))
            assertEquals("UNKNOWN",answer.text("response_type"))
            ui.onNodeWithText("目前记录还不足以回答").performScrollTo();shot("29-reader-unknown")
            tab("我的");ui.onNodeWithText("请记录者补充讲述").performScrollTo().performTextInput("会议演示：你小时候最喜欢的老师叫什么？愿意的话讲讲你们的故事。")
            click("提交问题请求");idle();shot("30-reader-request")
            switchAccount(person);tab("我的")
            val request=model.ui.value.requests.first{it.text("text").startsWith("会议演示：")}
            ui.onAllNodesWithText(request.text("text")).onFirst().performScrollTo();shot("31-owner-request")
            report("sharing",JSONObject().put("invitation_id",invite.getString("id")).put("episode_id",ep).put("reader_answer",answer.text("response_type")).put("request_id",request.text("request_id")).put("device_scope","two normal accounts sequentially on one emulator"))
            return
        }
        if(phase=="portraits"){
            tab("档案");click("人物")
            ui.onNodeWithText("记忆的八个侧面").performScrollTo();shot("17-eight-facets-top")
            ui.onNodeWithText("从四个视角了解").performScrollTo();shot("18-four-views")
            val oldJobs=model.ui.value.narrativeJobs.map{it.text("job_id")}.toSet()
            click("整理故事 / 留下寄语")
            check("将已核对的有效文字交由云端组织故事")
            click("整理选定讲述");idle();shot("19-organizing")
            ui.waitUntil(240_000){model.ui.value.narrativeJobs.any{it.text("job_id") !in oldJobs && it.text("status") in setOf("complete","failed")}}
            val job=model.ui.value.narrativeJobs.first{it.text("job_id") !in oldJobs}
            File(out,"narrative-result.json").writeText(model.ui.value.narrative.toString(2))
            File(out,"narrative-job.json").writeText(job.toString(2))
            assertEquals("complete",job.text("status"))
            click("收起整理工具")
            val pending=model.ui.value.narrative.rows("records").count{it.text("status") in setOf("pending","stale")}
            click("待核对 $pending 项")
            val views=model.ui.value.narrative.rows("views")
            views.forEachIndexed{index,view->
                click(view.text("title"))
                val rows=selectNarrativeRecords(model.ui.value.narrative.rows("records"),true,true,index,"","")
                if(rows.isNotEmpty())ui.onAllNodesWithText(rows.first().text("text")).onFirst().performScrollTo()
                else ui.onNodeWithText("暂时没有需要核对的建议。").performScrollTo()
                shot("20-view-$index")
            }
            click(views[2].text("title"))
            val observation=selectNarrativeRecords(model.ui.value.narrative.rows("records"),true,true,2,"","").firstOrNull()
            if(observation!=null){click("为什么这样整理 · 查看来源");shot("21-understanding-evidence")}
            report("portraits",JSONObject().put("records",model.ui.value.narrative.rows("records").size).put("job",job))
            return
        }
        if(phase=="record"){
            if(ui.activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                InstrumentationRegistry.getInstrumentation().uiAutomation.grantRuntimePermission(ui.activity.packageName,Manifest.permission.RECORD_AUDIO)
            }
            check("我同意本次麦克风录音");click("开始录音");idle()
            assertTrue(model.ui.value.recording)
            shot("03-recording")
            click("暂停录音");idle();assertTrue(model.ui.value.paused);shot("04-paused")
            click("继续录音");idle();assertFalse(model.ui.value.paused)
            File(out,"mic-start").writeText("fictional TTS injection requested")
            ui.waitUntil(80_000){File(out,"mic-done").exists()||File(out,"mic-error").exists()}
            click("停止并保留原音");idle();shot("05-saved")
            val capture=model.ui.value.local.first()
            File(capture.recording.audioPath).copyTo(File(out,"native-original.m4a"),overwrite=true)
            report("record",JSONObject().put("duration_ms",capture.recording.durationMillis).put("capture_key",capture.key))
            assertFalse("Microphone injection failed; do not upload silence",File(out,"mic-error").exists())
            click("播放本机原音")
            ui.waitUntil(25_000){model.audio.playback.value.playing&&model.audio.playback.value.positionMillis>1000}
            shot("06-local-playback");click("停止本机播放")
            File(out,"audio-ready").writeText("capture ready for host signal check")
            ui.waitUntil(45_000){File(out,"audio-checked").exists()}
            check("同意保存原音，并将本段完整音频");click("上传并等待核对");idle()
            val ep=model.ui.value.local.first().episode;assertTrue(ep.isNotBlank())
            File(out,"episode-id").writeText(ep)
            report("upload",JSONObject().put("episode_id",ep))
        }
        val ep=File(out,"episode-id").readText().trim()
        tab("档案")
        ui.waitUntil(240_000){model.ui.value.stories.any{it.text("episode_id")==ep&&(it.optBoolean("waiting_for_review")||it.text("status")=="ready"||it.text("status")=="failed")}}
        val current=model.ui.value.stories.first{it.text("episode_id")==ep}
        assertNotEquals("failed",current.text("status"));shot("07-asr-ready")
        if(current.optBoolean("waiting_for_review")){
            click("核对转写");idle();shot("08-transcript-review")
            val transcript=model.ui.value.reviewText
            assertTrue("ASR must contain real recognized text",transcript.length>15)
            File(out,"machine-transcript.txt").writeText(transcript)
            // Only technical acceptance of fictional audio; do not replace with script.
            check("我确认文字与补充说明");click("确认文字并整理");idle()
            shot("09-processing")
        }
        ui.waitUntil(240_000){model.ui.value.stories.any{it.text("episode_id")==ep&&it.text("status") in setOf("ready","failed")}}
        val story=model.ui.value.stories.first{it.text("episode_id")==ep}
        assertEquals("ready",story.text("status"));assertTrue(story.rows("memories").isNotEmpty())
        File(out,"story-result.json").writeText(story.toString(2));shot("10-story-ready")
        click("打开故事");shot("11-story-detail");click("播放完整原音")
        ui.waitUntil(30_000){model.ui.value.player.playing&&model.ui.value.player.position>1000}
        report("source-playback",JSONObject().put("position_ms",model.ui.value.player.position).put("duration_ms",model.ui.value.player.duration))
        shot("12-cloud-playback");click("停止播放")
        click("记忆");shot("13-memories")
        tab("对话")
        ui.onNodeWithText("想了解什么？").performTextReplacement(cfg.getString("question"))
        check("同意本次将问题和有权访问");click("提问");idle()
        val answer=checkNotNull(model.ui.value.answer);assertTrue(answer.text("answer").isNotBlank())
        File(out,"answer.json").writeText(answer.toString(2))
        val heading=when(answer.text("response_type")){"ORIGINAL"->"本人原话 · 核对文字";"SIMULATION"->"依据记录生成 · 不是本人原话";else->"目前记录还不足以回答"}
        ui.onNodeWithText(heading).performScrollTo();shot("14-answer")
        if(answer.rows("evidence").isNotEmpty()){click("播放来源完整原音");ui.waitUntil(30_000){model.ui.value.player.playing&&model.ui.value.player.position>1000};shot("15-answer-source");click("停止播放")}
        tab("档案");click("人物");shot("16-memory-map")
        ui.onNodeWithText("慢慢认识一个人").assertExists()
        report("complete",JSONObject().put("episode_id",ep).put("stt",story.text("stt_model_version")).put("llm",story.text("model_version")).put("memory_count",story.rows("memories").size).put("answer_type",answer.text("response_type")))
    }
}
