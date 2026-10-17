package me.remember.app

import android.content.Intent
import android.graphics.Bitmap
import android.media.AudioTrack
import android.os.ParcelFileDescriptor
import androidx.compose.ui.test.*
import androidx.compose.ui.semantics.SemanticsActions
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
            if(BuildConfig.DEMO_ACCOUNTS) {
                ui.runOnIdle{model.enterDemo("relative")}
                ui.waitUntil(90000){!model.ui.value.busy && model.ui.value.demoRole=="relative"}
            } else {
                ui.runOnIdle{if(model.ui.value.actor.isNotBlank())model.logout()}
                ui.waitUntil(30000){model.ui.value.actor.isBlank()}
                ui.onNodeWithText("账号").performTextReplacement(config.getString("username"))
                ui.onNodeWithText("密码（至少8个字符）").performTextReplacement(config.getString("password"))
                click("登录");ui.waitUntil(90000){!model.ui.value.busy&&model.ui.value.actor.isNotBlank()}
            }
            val space=model.ui.value.spaces.single{it.text("subject_id")==config.getString("subject_id")}
            if(model.ui.value.subject!=space.text("subject_id"))ui.runOnIdle{model.selectSpace(space)}
            ui.waitUntil(90000){!model.ui.value.busy&&!model.ui.value.spaceChoiceRequired}
            inst.uiAutomation.executeShellCommand("pm grant ${context.packageName} android.permission.RECORD_AUDIO").close()
            click("对话")
            val voiceMode=InstrumentationRegistry.getArguments().getString("voiceMode","evidence")
            if(voiceMode=="persona")click("与 AI 分身聊聊")
            report.put("mode",voiceMode)
            click("语音聊聊")
            val speed=InstrumentationRegistry.getArguments().getString("responseSpeed","reviewed")
            val voiceEngine=InstrumentationRegistry.getArguments().getString("voiceEngine","pipeline")
            if(voiceEngine=="step_realtime"){
                ui.waitUntil(15000){ui.onAllNodesWithTag("voice-realtime").fetchSemanticsNodes().isNotEmpty()}
                ui.onNodeWithTag("voice-realtime").performClick()
            }else if(speed!="reviewed")ui.onNodeWithTag("voice-fast").assertIsOff().performClick()
            report.put("response_speed",speed)
            report.put("voice_engine",voiceEngine)
            ui.waitUntil(15000){!model.ui.value.busy}
            click("开始")
            ui.waitUntil(90000){model.voiceCall.value?.ui?.value?.ready==true||model.ui.value.error!=null}
            assertNull(model.ui.value.error)
            val engine=checkNotNull(model.voiceCall.value)
            assertTrue(engine.ui.value.ready);shot("01-listening")
            if(InstrumentationRegistry.getArguments().getString("lifecycleOnly")=="true"){
                scenario.moveToState(Lifecycle.State.CREATED)
                ui.waitUntil(10000){engine.ui.value.paused}
                scenario.moveToState(Lifecycle.State.RESUMED)
                ui.waitUntil(10000){ui.onAllNodes(hasText("继续") and hasClickAction()).onFirst().isDisplayed()}
                ui.waitForIdle();Thread.sleep(1000) // allow the resumed window animation to finish before capture
                assertTrue(engine.ui.value.paused);shot("04-return-paused")
                report.put("background_remains_paused",true).put("resumed_controls_visible",true)
                click("结束");ui.waitUntil(10000){model.voiceCall.value==null}
                report.put("ended",true).put("ok",true)
                return
            }
            if(InstrumentationRegistry.getArguments().getString("timingDemo")=="true"){
                // Observe the installed application; never inject a transcript or answer.
                // The conversation is visible inline. Details only exists after
                // an answer; opening it before the first utterance is invalid.
                // Emulator streamAudio can disturb the Windows audio HAL. Keep an
                // exact copy of live received PCM instead, alongside AudioTrack
                // progress. This is a digital soundtrack, not speaker-loopback.
                val socketField=engine.javaClass.getDeclaredField("socket").apply{isAccessible=true}
                val ws=socketField.get(engine) as okhttp3.WebSocket
                val listenerField=ws.javaClass.getDeclaredField("listener").apply{isAccessible=true}
                val original=listenerField.get(ws) as okhttp3.WebSocketListener
                listenerField.set(ws,object:okhttp3.WebSocketListener(){
                    override fun onMessage(socket:okhttp3.WebSocket,text:String){
                        val event=JSONObject(text)
                        if(event.optString("type")=="audio"){
                            File(folder,"demo-turn-${event.getLong("turn_id")}.pcm").appendBytes(
                                android.util.Base64.decode(event.getString("data"),android.util.Base64.NO_WRAP))
                        }else File(folder,"demo-protocol.jsonl").appendText(event.put("received_epoch_ms",System.currentTimeMillis()).toString()+"\n")
                        original.onMessage(socket,text)
                    }
                    override fun onFailure(socket:okhttp3.WebSocket,t:Throwable,response:okhttp3.Response?){original.onFailure(socket,t,response)}
                    override fun onClosing(socket:okhttp3.WebSocket,code:Int,reason:String){original.onClosing(socket,code,reason)}
                    override fun onClosed(socket:okhttp3.WebSocket,code:Int,reason:String){original.onClosed(socket,code,reason)}
                })
                val events=org.json.JSONArray()
                fun mark(kind:String,round:Int,extra:JSONObject=JSONObject()){
                    synchronized(events){
                    events.put(extra.put("kind",kind).put("round",round).put("epoch_ms",System.currentTimeMillis()))
                    File(folder,"timing-events.json").writeText(events.toString(2))
                    }
                }
                val trackField=engine.javaClass.getDeclaredField("track").apply{isAccessible=true}
                var previousAnswer=""
                val appPcm=InstrumentationRegistry.getArguments().getString("appPcm")=="true"
                val interruptDemo=InstrumentationRegistry.getArguments().getString("interruptDemo")=="true"
                var interruptedTurn=-1L;var interruptionMarked=false
                val demoRounds=InstrumentationRegistry.getArguments().getString("timingRounds","2").toInt().coerceIn(1,8)
                val continueOnError=InstrumentationRegistry.getArguments().getString("continueOnError")=="true"
                var failedRounds=0
                if(appPcm){
                    report.put("synthetic_microphone_injection",false).put("instrumented_app_pcm",true)
                    // Bypass only the emulator HAL. ASR, answer and TTS remain real.
                    val paused=engine.javaClass.getDeclaredField("inputPaused").apply{isAccessible=true}
                    paused.setBoolean(engine,true)
                    val job=engine.javaClass.getDeclaredField("capture").apply{isAccessible=true}.get(engine) as? kotlinx.coroutines.Job
                    job?.cancel()
                    // Cancellation may already have released AudioRecord in its finally block.
                    runCatching { (engine.javaClass.getDeclaredField("recorder").apply{isAccessible=true}.get(engine) as? android.media.AudioRecord)?.stop() }
                    kotlinx.coroutines.runBlocking{job?.join()}
                    paused.setBoolean(engine,false)
                    val audio=(1..demoRounds).map{r->ParcelFileDescriptor.AutoCloseInputStream(inst.uiAutomation.executeShellCommand("cat /data/local/tmp/voice-demo-input-$r.pcm")).use{it.readBytes()}}
                    check(audio.all{it.isNotEmpty()&&it.size%2==0})
                    Thread{
                        var round=1;var offset=-1;var tick=System.nanoTime()
                        while(engine.ui.value.active){
                            if(round<=demoRounds&&offset<0&&File(folder,"demo-start-$round").exists()){
                                offset=0;mark("question_started",round)
                            }
                            val bytes=if(offset>=0&&round<=demoRounds){
                                val pcm=audio[round-1];val end=minOf(offset+640,pcm.size)
                                pcm.copyOfRange(offset,end).also{offset=end}
                            }else ByteArray(640)
                            engine.acceptCapturedPcm(bytes)
                            tick+=20_000_000L
                            val delay=(tick-System.nanoTime())/1_000_000
                            if(delay>0)Thread.sleep(delay)
                            if(offset>=0&&round<=demoRounds&&offset>=audio[round-1].size){
                                mark("question_input_ended",round);round++;offset=-1
                            }
                        }
                    }.apply{isDaemon=true;start()}
                }else{
                File(folder,"demo-connect-mic").writeText("register virtual microphone")
                ui.waitUntil(20000){File(folder,"demo-microphone-connected").exists()}
                // Reopen AudioRecord after the emulator virtual microphone exists.
                click("暂停");ui.waitUntil(10000){engine.ui.value.paused}
                click("继续");ui.waitUntil(20000){!engine.ui.value.paused&&engine.ui.value.error.isBlank()}
                Thread.sleep(500)
                }
                for(round in 1..demoRounds){
                    mark("ready_for_question",round)
                    File(folder,"demo-ready-$round").writeText("inject synthetic question")
                    var transcript="";var answerSeen=false;var audioSeen=false;var completed=false
                    var roundFailed=false;var priorErrorCleared=engine.ui.value.error.isBlank()
                    var lastAnswerText=""
                    val deadline=System.currentTimeMillis()+65000
                    var lastSample=0L;var lastProgress=0L
                    while(System.currentTimeMillis()<deadline){
                        val s=engine.ui.value
                        if(System.currentTimeMillis()-lastProgress>=50){
                            lastProgress=System.currentTimeMillis()
                            val pos=runCatching{(trackField.get(engine) as? AudioTrack)?.playbackHeadPosition?:0}.getOrDefault(0)
                            if(pos>0){
                                val tf=engine.javaClass.getDeclaredField("trackTurn").apply{isAccessible=true}
                                mark("playback_progress",round,JSONObject().put("turn_id",tf.getLong(engine)).put("played_samples",pos))
                            }
                        }
                        // The capture path publishes these fields while holding the engine monitor.
                        // Read one snapshot, after flush finishes, rather than mixing two interrupts.
                        val interruptSnapshot=synchronized(engine){Triple(engine.lastInterruptedTurn,engine.lastInterruptedSamples,engine.lastInterruptEpochMs)}
                        if(interruptDemo&&round==2&&!interruptionMarked&&interruptSnapshot.first==interruptedTurn&&interruptSnapshot.second>0){
                            mark("playback_interrupted",1,JSONObject().put("turn_id",interruptedTurn)
                                .put("played_samples",interruptSnapshot.second).put("stopped_epoch_ms",interruptSnapshot.third))
                            interruptionMarked=true
                        }
                        if(System.currentTimeMillis()-lastSample>=1000){
                            lastSample=System.currentTimeMillis()
                            mark("microphone",round,JSONObject().put("samples",engine.capturedSamples).put("rms",engine.lastInputRms))
                        }
                        if(s.transcript!=transcript&&s.transcript.isNotBlank()){
                            transcript=s.transcript;mark("transcript",round,JSONObject().put("text",transcript))
                            ui.waitForIdle() // Compose test clock must render the actual state change.
                        }
                        if(s.error.isBlank())priorErrorCleared=true
                        if(s.error.isNotBlank()&&priorErrorCleared){
                            mark("error",round,JSONObject().put("message",s.error));shot("demo-$round-error")
                            if(!continueOnError)fail(s.error)
                            failedRounds++;roundFailed=true;break
                        }
                        val answerId=s.sources?.let{it.optString("answer_id").ifBlank{it.optString("live_turn_id")}.ifBlank {
                            if(it.optString("response_type")=="CONVERSATION") "conversation:"+engine.javaClass.getDeclaredField("turn").apply{isAccessible=true}.getLong(engine) else ""
                        }}.orEmpty()
                        if(answerId.isNotBlank()&&answerId!=previousAnswer){
                            if(!answerSeen||s.answer!=lastAnswerText){
                                mark("answer_visible",round,JSONObject().put("text",s.answer).put("answer_id",answerId))
                                answerSeen=true;lastAnswerText=s.answer;ui.waitForIdle()
                            }
                            val played=runCatching{(trackField.get(engine) as? AudioTrack)?.playbackHeadPosition?:0}.getOrDefault(0)
                            if(played>0&&!audioSeen){
                                val turnField=engine.javaClass.getDeclaredField("trackTurn").apply{isAccessible=true}
                                mark("audio_track_started",round,JSONObject().put("turn_id",turnField.getLong(engine)).put("played_samples",played))
                                audioSeen=true;ui.waitForIdle();shot("demo-$round-answer")
                            }
                            if(interruptDemo&&round==1&&audioSeen&&played>=14400){
                                interruptedTurn=engine.javaClass.getDeclaredField("trackTurn").apply{isAccessible=true}.getLong(engine)
                                mark("interrupt_ready",round);previousAnswer=answerId;completed=true;break
                            }
                            if(audioSeen&&s.status=="我在听"){
                                mark("playback_finished",round);previousAnswer=answerId;completed=true;break
                            }
                        }
                        Thread.sleep(25)
                    }
                    assertTrue("Round $round did not complete playback",roundFailed||(answerSeen&&audioSeen&&completed))
                    if(!(interruptDemo&&round==1))Thread.sleep(1000)
                }
                if(interruptDemo)assertTrue("Local VAD did not stop the previous playing turn",interruptionMarked)
                if(!interruptDemo&&demoRounds>1){
                    val earlier=engine.ui.value.history
                    assertTrue("Earlier call questions disappeared",earlier.size>=demoRounds-1)
                    ui.onNodeWithTag("voice-history").performScrollToIndex(0)
                    ui.waitForIdle();Thread.sleep(400)
                    ui.onNodeWithText(earlier.first().question).assertIsDisplayed()
                    shot("demo-history-retained")
                    report.put("retained_exchanges",earlier.size+1)
                    ui.onNodeWithTag("voice-history").performScrollToIndex(earlier.size)
                }
                if(InstrumentationRegistry.getArguments().getString("entrustedRecall")=="true"){
                    assertEquals(0,failedRounds)
                    val sources=checkNotNull(engine.ui.value.sources)
                    assertTrue("Last real answer must have an authorized recall",sources.getJSONArray("recall_actions").length()>0)
                    ui.onNodeWithTag("open-entrusted-letter").performScrollTo().performClick()
                    ui.waitUntil(20000){model.ui.value.openedLetter!=null||model.ui.value.error!=null}
                    assertNull(model.ui.value.error);assertTrue(engine.ui.value.paused)
                    val letter=checkNotNull(model.ui.value.openedLetter)
                    report.put("recall_letter_id",letter.getString("id"));shot("demo-letter-sealed")
                    ui.onNodeWithText("轻触拆开").performClick()
                    ui.onNodeWithText(letter.getString("title")).assertIsDisplayed()
                    ui.onNodeWithText(letter.getString("author_display_name")).performScrollTo().assertIsDisplayed()
                    shot("demo-letter-opened")
                    ui.onNodeWithTag("letter-play").performScrollTo().performClick()
                    ui.waitUntil(30000){model.ui.value.player.playing&&model.ui.value.player.duration>0}
                    ui.waitUntil(10000){model.ui.value.player.position>500}
                    val duration=model.ui.value.player.duration
                    report.put("letter_audio_duration_ms",duration);shot("demo-letter-playing")
                    ui.onNodeWithTag("letter-play").performClick()
                    ui.waitUntil(10000){!model.ui.value.player.playing}
                    ui.onNode(SemanticsMatcher.keyIsDefined(SemanticsActions.SetProgress)).performScrollTo().performSemanticsAction(SemanticsActions.SetProgress){it(duration*.5f)}
                    ui.waitUntil(10000){kotlin.math.abs(model.ui.value.player.position-duration/2)<1500}
                    shot("demo-letter-seeked")
                    ui.onNodeWithTag("letter-play").performScrollTo().performClick()
                    ui.waitUntil(10000){model.ui.value.player.playing};Thread.sleep(1500)
                    ui.onNodeWithContentDescription("关闭信笺").performClick()
                    ui.waitUntil(10000){model.ui.value.openedLetter==null&&!model.ui.value.player.playing}
                    assertTrue(model.ui.value.player.episode.isBlank())
                    report.put("authorized_recall_opened",true).put("real_audio_pause_seek_resume_close",true)
                }
                click("结束");ui.waitUntil(10000){model.voiceCall.value==null}
                report.put("ok",failedRounds==0).put("failed_rounds",failedRounds).put("all_rounds_attempted",true).put("timing_demo",true).put("events",events)
                assertEquals("Completed the batch but retained failed replies",0,failedRounds)
                return
            }
            File(folder,"ready").writeText("inject synthetic question now")
            ui.waitUntil(150000){engine.ui.value.answer.isNotBlank()||engine.ui.value.error.isNotBlank()}
            assertEquals("",engine.ui.value.error)
            report.put("recognized",engine.ui.value.transcript).put("answer",engine.ui.value.answer)
            val trackField=engine.javaClass.getDeclaredField("track").apply{isAccessible=true}
            ui.waitUntil(30000){runCatching{(trackField.get(engine) as? AudioTrack)?.playbackHeadPosition?:0}.getOrDefault(0)>0}
            report.put("audio_track_advanced",true)
            ui.onNodeWithTag("voice-details").performClick();shot("02-response");click("收起")
            val oldTrack=trackField.get(engine) as AudioTrack
            val oldAnswerId=checkNotNull(engine.ui.value.sources).getString("answer_id")
            File(folder,"interrupt-ready").writeText("inject second question during playback")
            ui.waitUntil(150000){
                val state=engine.ui.value
                val answerId=state.sources?.optString("answer_id").orEmpty()
                state.error.isNotBlank() || (state.transcript.contains("女儿") && state.answer.contains("陈岚") &&
                    answerId.isNotBlank() && answerId!=oldAnswerId)
            }
            assertEquals("",engine.ui.value.error)
            report.put("new_answer_id",engine.ui.value.sources?.getString("answer_id"))
            assertTrue(runCatching{oldTrack.playState!=AudioTrack.PLAYSTATE_PLAYING}.getOrDefault(true))
            report.put("interrupted_answer",engine.ui.value.answer).put("old_track_stopped",true)
            shot("03-interrupted-response")
            click("暂停");ui.waitUntil(10000){engine.ui.value.paused};shot("03-paused")
            click("继续");ui.waitUntil(15000){!engine.ui.value.paused}
            scenario.moveToState(Lifecycle.State.CREATED)
            ui.waitUntil(10000){engine.ui.value.paused}
            scenario.moveToState(Lifecycle.State.RESUMED)
            ui.waitUntil(10000){ui.onAllNodes(hasText("继续") and hasClickAction()).onFirst().isDisplayed()}
            ui.waitForIdle();Thread.sleep(1000)
            assertTrue(engine.ui.value.paused)
            report.put("background_remains_paused",true);shot("04-return-paused")
            click("结束");ui.waitUntil(10000){model.voiceCall.value==null}
            report.put("ended",true).put("ok",true)
        }catch(error:Throwable){
            report.put("ok",false).put("failure_type",error.javaClass.simpleName)
            runCatching{model.voiceCall.value?.ui?.value}.getOrNull()?.let{state->
                report.put("last_transcript",state.transcript).put("last_error",state.error)
            }
            shot("failure");throw error
        }finally{File(folder,"result.json").writeText(report.toString(2));scenario.close()}
    }
}
