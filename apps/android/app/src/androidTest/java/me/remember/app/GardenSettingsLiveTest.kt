package me.remember.app

import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import me.remember.app.integration.*
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.security.MessageDigest

/** Opt-in real ECS + exact internal APK. Fictional imported audio; no planted model answers. */
class GardenSettingsLiveTest {
    @get:Rule val ui=createAndroidComposeRule<MainActivity>()
    private val model get()=ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
    private val automation get()=InstrumentationRegistry.getInstrumentation().uiAutomation
    private val out get()=File(ui.activity.getExternalFilesDir(null),"garden-settings").apply { mkdirs() }
    private fun idle(){ui.waitUntil(90_000){!model.ui.value.busy};assertNull(model.ui.value.error)}
    private fun click(text:String){
        val match=hasText(text) and isEnabled()
        ui.waitUntil(30_000){ui.onAllNodes(match).fetchSemanticsNodes().isNotEmpty()}
        val n=ui.onAllNodes(match).onFirst();if(!n.isDisplayed())n.performScrollTo();n.performClick()
    }
    private fun tab(text:String)=ui.onNodeWithText(text,useUnmergedTree=true).performClick()
    private fun shot(name:String){ui.waitForIdle();Thread.sleep(400)
        val bitmap=automation.takeScreenshot();File(out,"$name.png").outputStream().use{bitmap.compress(Bitmap.CompressFormat.PNG,100,it)};bitmap.recycle()}
    private fun logout(){tab("我的");click("账号与空间");click("退出登录 / 换个账号");click("确认");ui.waitUntil(30_000){model.ui.value.actor.isBlank()};idle()}
    private fun login(person:JSONObject){
        if(model.ui.value.actor.isNotBlank())logout()
        ui.onNodeWithText("账号").performScrollTo().performTextReplacement(person.getString("username"))
        ui.onNodeWithText("密码（至少8个字符）").performScrollTo().performTextInput(person.getString("password"));click("登录")
        ui.waitUntil(60_000){model.ui.value.actor==person.getString("actor_id")||model.ui.value.error!=null};idle()
    }
    private fun digest(file:File)=MessageDigest.getInstance("SHA-256").digest(file.readBytes()).toList()
    @Test fun realFlowersPlaybackSettingsIdentityAndRevocation(){
        val cfg=JSONObject(ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand("cat /data/local/tmp/remember-garden-settings.json")).bufferedReader().use{it.readText()})
        require(!BuildConfig.DEBUG);require(BuildConfig.SERVICE_URL=="https://39.108.183.47")
        idle();login(cfg.getJSONObject("owner"));assertTrue(model.ui.value.owner)
        val ep=cfg.getString("episode");val subject=model.ui.value.subject
        val clusterId=projectGarden(model.ui.value.stories,model.ui.value.narrative).first{ep in it.episodeIds}.id
        tab("档案");click("记忆");shot("01-native-garden")
        ui.onNodeWithTag("garden-cluster-$clusterId").performScrollTo().performClick();shot("02-flower-petals")
        val projected=projectGarden(model.ui.value.stories,model.ui.value.narrative).first{ep in it.episodeIds}
        click(projected.petals.first().title);shot("03-memory-evidence")
        click("听完整原音 · ${recordingDate(model.ui.value.stories.first{it.text("episode_id")==ep}.text("recorded_at"))}")
        ui.waitUntil(35_000){model.ui.value.player.playing && model.ui.value.player.position>1000 || model.ui.value.error!=null};assertNull(model.ui.value.error)
        click("暂停");assertFalse(model.ui.value.player.playing);ui.runOnIdle{model.seekSource(2000)};shot("04-source-player")
        click("返回花朵");click("返回花田");ui.onNodeWithTag("garden-cluster-$clusterId").assertIsDisplayed()
        tab("我的");shot("05-settings-home");click("外观与阅读");click("深色");click("林间");shot("06-dark-appearance")
        ui.activityRule.scenario.recreate();idle()
        assertEquals(ThemeChoice.DARK,AppearancePreferences(ui.activity).choices.value.theme)
        assertEquals(SceneChoice.FOREST,AppearancePreferences(ui.activity).choices.value.scene)
        tab("我的");click("外观与阅读");click("浅色");click("按页面自然场景");click("返回我的")
        click("设备权限与提醒");shot("07-device-permissions");click("打开系统权限设置");Thread.sleep(500)
        automation.executeShellCommand("input keyevent 4").close();ui.waitForIdle();click("返回我的")
        // A real short microphone recording is retained locally, never uploaded or passed as spoken data.
        automation.executeShellCommand("pm grant me.remember.app.internal android.permission.RECORD_AUDIO").close()
        tab("今天")
        ui.onAllNodes(isToggleable() and hasAnySibling(hasText("我同意本次麦克风录音，原音保存于此设备。"))).onFirst().performScrollTo().performClick()
        click("开始录音");ui.waitUntil(15_000){model.ui.value.recording};Thread.sleep(2300);click("停止并保留原音");idle()
        val original=File(model.ui.value.local.first().recording.audioPath);val before=digest(original)
        tab("我的");click("数据与帮助");click("检查服务连接")
        ui.waitUntil(20_000){model.ui.value.connectionCheck.phase==ConnectionPhase.READY}
        ui.runOnIdle{model.playSource(ep)}
        ui.waitUntil(30_000){model.ui.value.player.playing && model.ui.value.player.position>500}
        assertTrue(File(ui.activity.cacheDir,"native-source-audio").listFiles().orEmpty().isNotEmpty())
        click("清理下载缓存");click("确认");assertTrue(original.isFile);assertEquals(before,digest(original));assertTrue(File(ui.activity.cacheDir,"native-source-audio").listFiles().orEmpty().isEmpty());shot("08-data-help")
        click("返回我的");logout();login(cfg.getJSONObject("reader"))
        val target=model.ui.value.spaces.first{it.text("subject_id")==subject};ui.runOnIdle{model.selectSpace(target)};idle();assertFalse(model.ui.value.owner)
        tab("档案");click("记忆");ui.onNodeWithTag("garden-cluster-$clusterId").performScrollTo().performClick();shot("09-reader-flower")
        // Revoke only this dedicated synthetic test grant through the owner's real API.
        val ownerGate=SessionGate();val ownerSession=ownerGate.connect(BuildConfig.SERVICE_URL,cfg.getJSONObject("owner").getString("token"))
        BackendClient(ownerGate).json(ownerSession,"/api/v1/workbench/subjects/$subject/grants/${cfg.getString("grant")}","DELETE")
        ui.runOnIdle{model.refresh()};idle();assertFalse(model.ui.value.stories.any{it.text("episode_id")==ep});ui.onNodeWithTag("garden-cluster-$clusterId").assertDoesNotExist();shot("10-revoked-garden")
        val current=checkNotNull(SavedSession(ui.activity).load())
        accountRequest(current.first,"logout",token=current.second)
        ui.runOnIdle{model.refresh()};ui.waitUntil(30_000){model.ui.value.actor.isBlank()}
        assertNull(SavedSession(ui.activity).load());assertTrue(model.ui.value.stories.isEmpty());ui.onNodeWithText("密码（至少8个字符）").assertExists();shot("11-session-expired")
        File(out,"result.json").writeText(JSONObject().put("version",BuildConfig.VERSION_NAME).put("exact_internal_apk",true).put("ecs_ip_https",true)
            .put("flower_petal_evidence_playback",true).put("appearance_restart",true).put("cache_preserved_original",true)
            .put("ordinary_owner_reader",true).put("revoke_removed_flower",true).put("expired_session_login",true)
            .put("emulator",true).put("physical_phone",false).put("ios",false).put("synthetic_import",true).put("local_microphone_test_uploaded",false).toString(2))
    }
    @Test fun largeFontMemoryReadAndReturn(){
        val cfg=JSONObject(ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand("cat /data/local/tmp/remember-garden-settings.json")).bufferedReader().use{it.readText()})
        assumeTrue("Run explicitly with system font_scale=2, restore afterward",ui.activity.resources.configuration.fontScale>=1.9f)
        idle();login(cfg.getJSONObject("owner"));tab("档案");click("记忆")
        val ep=cfg.getString("episode");val c=projectGarden(model.ui.value.stories,model.ui.value.narrative).first{ep in it.episodeIds}
        ui.onNodeWithTag("garden-cluster-${c.id}").performScrollTo().performClick()
        val p=c.petals.first()
        click(p.title);shot("12-large-font-memory")
        ui.onNodeWithText("听完整原音 · ${recordingDate(model.ui.value.stories.first{it.text("episode_id")==ep}.text("recorded_at"))}").assertIsDisplayed()
        click("返回花朵");click("返回花田");ui.onNodeWithTag("garden-cluster-${c.id}").assertExists()
        File(out,"large-font-result.json").writeText(JSONObject().put("font_scale",ui.activity.resources.configuration.fontScale)
            .put("open_memory",true).put("source_button_visible",true).put("return_to_garden",true).put("emulator",true).toString(2))
    }
    @Test fun confirmActualSourcesThenReadOrganizedFlower(){
        val cfg=JSONObject(ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand("cat /data/local/tmp/remember-garden-settings.json")).bufferedReader().use{it.readText()})
        idle();login(cfg.getJSONObject("owner"));val subject=model.ui.value.subject
        val sources=model.ui.value.narrative.rows("source_evidence").filter{it.text("episode_id")==cfg.getString("episode")}
        assertTrue(sources.isNotEmpty())
        val current=checkNotNull(SavedSession(ui.activity).load());val gate=SessionGate();val s=gate.connect(current.first,current.second)
        val record=BackendClient(gate).json(s,"/api/v1/workbench/subjects/$subject/narrative/records","POST",
            JSONObject().put("kind","story").put("title","一次关于家人安全的讲述")
                .put("text",sources.joinToString("\n"){it.text("excerpt")})
                .put("facets",JSONArray(listOf("VALUES","EXPRESSION")))
                .put("evidence_ids",JSONArray(sources.map{it.text("evidence_id")})))
        ui.runOnIdle{model.refresh()};idle();tab("档案");click("人物");click("在意与选择")
        click("待核对 ${model.ui.value.narrative.rows("records").count{it.text("status")=="pending"}} 项")
        click("为什么这样整理 · 查看来源");shot("13-organized-source-review")
        click("核对无误，确认整理");idle()
        assertEquals("confirmed",model.ui.value.narrative.rows("records").first{it.text("id")==record.text("id")}.text("status"))
        click("记忆");ui.onNodeWithTag("garden-cluster-record:${record.text("id")}").performScrollTo().performClick();shot("14-confirmed-story-flower")
        logout();login(cfg.getJSONObject("reader"))
        ui.runOnIdle{model.selectSpace(model.ui.value.spaces.first{it.text("subject_id")==subject})};idle()
        tab("档案");click("记忆");ui.onNodeWithTag("garden-cluster-record:${record.text("id")}").performScrollTo().performClick();shot("15-reader-organized-story")
        File(out,"organized-result.json").writeText(JSONObject().put("api_draft_setup",true).put("draft_text_from_actual_sources",true)
            .put("app_confirmation_clicked",true).put("confirmed_flower_clicked",true).put("reader_organized_flower_clicked",true)
            .put("new_narrative_model_call",false).put("emulator",true).toString(2))
    }
}
