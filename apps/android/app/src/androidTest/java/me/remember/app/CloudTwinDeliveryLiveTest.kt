package me.remember.app

import android.content.Intent
import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
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
import java.time.Instant

/** Opt-in cloud delivery acceptance on the signed internal APK. No fixtures or provider retries.
 * Login, space selection, persona question, consent, playback controls and logout use Compose UI.
 * Saved-answer/asset loading uses the existing production model because there is no history UI.
 * Authenticated GETs independently verify identity, release and persisted answer provenance.
 */
class CloudTwinDeliveryLiveTest {
    @get:Rule val ui = createEmptyComposeRule()
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private lateinit var activity: MainActivity
    private lateinit var model: NativeWorkbenchModel
    private lateinit var folder: File
    private lateinit var result: JSONObject
    private var password = ""
    private var token = ""
    private var step = "configuration"
    private var role = ""

    private fun redact(value: String): String = value
        .let { if(password.isNotEmpty()) it.replace(password, "[redacted]") else it }
        .let { if(token.isNotEmpty()) it.replace(token, "[redacted]") else it }

    private fun persist() { File(folder, "result.json").writeText(result.toString(2)) }
    private fun event(name: String, detail: JSONObject = JSONObject()) {
        step = name
        result.getJSONArray("events").put(JSONObject().put("name", name).put("at", Instant.now().toString()).put("detail", detail))
        persist()
    }
    private fun idle(timeout: Long = 90_000) {
        ui.waitUntil(timeout) { !model.ui.value.busy }
        ui.waitForIdle()
        assertTrue("$step: ${redact(model.ui.value.error.orEmpty())}", model.ui.value.error == null)
    }
    private fun readAction(name: String, action: () -> Unit) {
        event(name)
        // Polling can acquire busy between a preceding idle() and the next action.
        // Retry only acquiring the idle slot; the read/play action itself is invoked once.
        ui.waitUntil(90_000) {
            var started = false
            ui.runOnIdle { if(!model.ui.value.busy) { action(); started = true } }
            started
        }
        idle(240_000)
    }
    private fun click(matcher: SemanticsMatcher) {
        ui.waitUntil(30_000) { ui.onAllNodes(matcher and hasClickAction()).fetchSemanticsNodes().isNotEmpty() }
        var node = ui.onAllNodes(matcher and hasClickAction()).onFirst()
        if(!node.isDisplayed()) node.performScrollTo()
        ui.waitUntil(90_000) {
            !model.ui.value.busy && ui.onAllNodes(matcher and hasClickAction() and isEnabled()).fetchSemanticsNodes().isNotEmpty()
        }
        node = ui.onAllNodes(matcher and hasClickAction() and isEnabled()).onFirst()
        node.performClick()
        ui.waitForIdle()
    }
    private fun click(label: String) = click(hasText(label))
    private fun reveal(node: SemanticsNodeInteraction) {
        node.performScrollTo(); ui.waitForIdle()
        val viewports = ui.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.VerticalScrollAxisRange))
        if(viewports.fetchSemanticsNodes().size == 1) {
            val viewport = viewports.onFirst()
            val delta = node.fetchSemanticsNode().boundsInRoot.top - viewport.fetchSemanticsNode().boundsInRoot.top
            if(delta > 0) viewport.performSemanticsAction(SemanticsActions.ScrollBy) { it(0f, delta) }
        }
        ui.waitForIdle()
    }
    private fun shot(name: String) {
        // Capture failures too; never call idle/assertNull from failure reporting.
        ui.waitForIdle()
        val bitmap = checkNotNull(instrumentation.uiAutomation.takeScreenshot())
        try { File(folder, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) } }
        finally { bitmap.recycle() }
    }
    private fun get(path: String): JSONObject {
        val saved = checkNotNull(SavedSession(activity).load()) { "Expected ordinary account session" }
        assertEquals(SERVER, saved.first)
        token = saved.second
        val gate = SessionGate()
        val session = gate.connect(saved.first, saved.second)
        return try { BackendClient(gate).json(session, path) } finally { gate.clear() }
    }
    private fun logout() {
        if(model.ui.value.actor.isNotBlank()) {
            if(model.ui.value.spaceChoiceRequired) click("退出账号")
            else {
                click("我的")
                if(ui.onAllNodes(hasText("退出登录 / 换个账号") and hasClickAction()).fetchSemanticsNodes().isEmpty()) click("账号与空间")
                click("退出登录 / 换个账号"); click("确认")
            }
        }
        ui.waitUntil(30_000) { model.ui.value.actor.isBlank() }
        assertNull("Saved login must be removed", SavedSession(activity).load())
        val state = model.ui.value
        assertTrue(state.spaces.isEmpty()); assertTrue(state.stories.isEmpty())
        assertTrue(state.subject.isBlank()); assertTrue(state.narrative.length() == 0)
        assertTrue(state.companion.length() == 0); assertTrue(state.voiceProfile.length() == 0)
        assertNull(state.answer); assertTrue(state.player.episode.isBlank()); assertFalse(state.player.playing)
        assertTrue("Downloaded source/answer cache must be empty after logout",
            File(activity.cacheDir, "native-source-audio").listFiles().orEmpty().isEmpty())
    }

    @Test fun ordinaryOwnerAndReaderOverVerifiedCloudHttps() {
        assertFalse("Cloud acceptance must fail on a debug APK", BuildConfig.DEBUG)
        assertEquals("internal", BuildConfig.BUILD_TYPE)
        assertEquals(SERVER, BuildConfig.SERVICE_URL)
        val config = try {
            JSONObject(ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation
                .executeShellCommand("cat /data/local/tmp/remember-cloud-twin.json"))
                .bufferedReader().use { it.readText() })
        } catch(_: Exception) { throw AssertionError("Missing or invalid /data/local/tmp/remember-cloud-twin.json; configuration is never logged") }
        assertTrue("Explicit cloud acceptance authorization required", config.getBoolean("execute_authorized"))
        val runId = config.getString("run_id")
        require(runId.matches(Regex("[a-zA-Z0-9_-]{1,80}"))) { "run_id must be a safe, unique delivery run label" }
        require(config.getString("expected_release_id").isNotBlank())
        val phases = config.rows("phases")
        require(phases.map { it.getString("role") } in listOf(listOf("owner"), listOf("reader"), listOf("owner", "reader")))
        phases.forEach {
            require(it.getString("subject_id").isNotBlank() && it.getString("expected_actor_id").isNotBlank())
            require(it.getString("username").isNotBlank() && it.getString("password").length >= 8)
            require(it.getString("episode_id").isNotBlank())
            val asking = it.optBoolean("ask_new", false)
            require(!asking || config.optBoolean("allow_new_question", false)) { "New questions require allow_new_question" }
            require(!asking || it.getString("question").trim().length in 1..1000)
            require(!it.optBoolean("play_new_answer_voice", false) || asking)
            val savedVoice = it.optBoolean("play_saved_answer_voice", false)
            require(!savedVoice || (!asking && it.optString("saved_answer_id").isNotBlank())) {
                "Saved-answer speech requires saved_answer_id and ask_new=false; do not re-ask a completed question"
            }
            require(!it.optBoolean("read_only", it.getString("role") == "reader") ||
                (!asking && !it.optBoolean("allow_enable_style", false) && !it.optBoolean("play_new_answer_voice", false) && !savedVoice))
            require(it.optString("saved_asset_id").isBlank() || it.optString("saved_answer_id").isNotBlank())
        }
        phases.forEach { phase -> runPhase(config, phase, runId) }
    }

    private fun runPhase(config: JSONObject, phase: JSONObject, runId: String) {
        role = phase.getString("role"); password = phase.getString("password"); token = ""
        val context = instrumentation.targetContext
        folder = File(checkNotNull(context.getExternalFilesDir(null)), "cloud-twin/$role").apply { mkdirs() }
        result = JSONObject().put("run_id", runId).put("role", role).put("server", SERVER)
            .put("build_type", BuildConfig.BUILD_TYPE).put("debuggable", BuildConfig.DEBUG)
            .put("app_version", BuildConfig.VERSION_NAME).put("app_version_code", BuildConfig.VERSION_CODE)
            .put("fixture", false).put("physical_phone", false).put("new_asr", false)
            .put("tls_validation", "Android default TLS with internal APK trust configuration; no test override")
            .put("interaction_method", "Compose UI; saved-answer/asset reads use production model; verification uses authenticated GET")
            .put("new_question_attempts", 0).put("new_speech_attempts", 0).put("style_changed", false)
            .put("saved_answer_played", false).put("new_answer_played", false).put("source_played", false)
            .put("logout_cache_cleared", false).put("status", "running").put("events", JSONArray())
        persist()
        val scenario = ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java))
        var failure: Throwable? = null
        try {
            scenario.onActivity { activity = it; model = ViewModelProvider(it)[NativeWorkbenchModel::class.java] }
            ui.waitUntil(90_000) { !model.ui.value.busy }
            if(model.ui.value.actor.isNotBlank()) logout()
            event("ordinary_login")
            ui.onNodeWithText("连接设置 / 开发身份").assertDoesNotExist()
            ui.onNodeWithText("账号").performTextReplacement(phase.getString("username"))
            ui.onNodeWithText("密码（至少8个字符）").performTextReplacement(password)
            click("登录")
            ui.waitUntil(90_000) { (!model.ui.value.busy && model.ui.value.actor.isNotBlank()) || model.ui.value.error != null }
            idle(); assertEquals(SERVER, checkNotNull(SavedSession(activity).load()).first)
            val subject = phase.getString("subject_id")
            val identity = get("/api/v1/workbench/spaces")
            val apiSpace = identity.rows().single { it.text("subject_id") == subject }
            assertEquals(phase.getString("expected_actor_id"), identity.text("actor_id"))
            assertEquals(identity.text("actor_id"), model.ui.value.actor)
            assertEquals(role, apiSpace.text("role"))
            result.put("api_actor_id", identity.text("actor_id")).put("api_display_name", identity.text("display_name"))
                .put("api_subject_id", subject).put("api_role", apiSpace.text("role")).put("ordinary_login", true)
            val version = get("/api/v1/service-info")
            result.put("server_release_id", version.text("release_id")).put("api_version", version.text("api_version")); persist()
            assertEquals("Do not run Twin acceptance against the previous deployment", config.getString("expected_release_id"), version.text("release_id"))
            assertTrue(version.text("api_version").isNotBlank())
            if(model.ui.value.subject != subject) {
                if(model.ui.value.spaceChoiceRequired) click(hasTestTag("choose-space-$subject"))
                else { click(hasTestTag("space-chooser")); click(hasTestTag("space-$subject")) }
                ui.waitUntil(90_000) { model.ui.value.subject == subject && !model.ui.value.busy }
                idle()
            }
            assertEquals(subject, model.ui.value.subject); assertEquals(role == "owner", model.ui.value.owner)
            if(activity.getSharedPreferences("remember-appearance", 0).getBoolean("simple_mode", false)) {
                click("我的"); click("简明模式"); idle()
            }
            result.put("font_scale", activity.resources.configuration.fontScale)
                .put("confirmed_understandings", confirmedUnderstandings(model.ui.value.narrative).size)
                .put("stories", model.ui.value.stories.size).put("voice_ready", model.ui.value.voiceProfile.optBoolean("ready"))
            assertTrue("Required confirmed understandings missing", confirmedUnderstandings(model.ui.value.narrative).size >= phase.optInt("minimum_understandings", 1))
            event("native_pages")
            click("档案"); click("花田"); idle(); shot("01-garden")
            click("人物"); idle(); shot("02-person")
            click("对话"); idle(); shot("03-dialogue")

            val styleBefore = model.ui.value.narrative.optJSONObject("style")?.optBoolean("enabled") == true
            result.put("style_enabled_before", styleBefore)
            if(role == "owner") {
                click("对话工具")
                val styleToggle = hasText(STYLE) and isToggleable()
                ui.onNode(styleToggle).assertExists()
                if(!styleBefore && phase.optBoolean("allow_enable_style", false)) {
                    event("owner_enable_style"); click(styleToggle); idle()
                    assertTrue(model.ui.value.narrative.getJSONObject("style").getBoolean("enabled"))
                    result.put("style_changed", true)
                }
                if(model.ui.value.narrative.optJSONObject("style")?.optBoolean("enabled") == true) ui.onNode(styleToggle).assertIsOn()
                shot("04-owner-style")
            } else ui.onNodeWithText(STYLE).assertDoesNotExist()
            result.put("style_enabled_after", model.ui.value.narrative.optJSONObject("style")?.optBoolean("enabled") == true)

            phase.optString("saved_answer_id").takeIf { it.isNotBlank() }?.let { id ->
                readAction("saved_answer_read") { model.openSavedAnswer(id) }
                val answer = checkNotNull(model.ui.value.answer)
                assertEquals(id, answer.text("answer_id")); verifyAnswer(answer, subject, requirePersona = true)
                result.put("saved_answer", answerRecord(answer)); reveal(ui.onNodeWithText(answer.text("answer"))); shot("05-saved-answer")
                click("查看理解与来源")
                val source = ui.onAllNodesWithText("依据：${answer.rows("evidence").first().text("excerpt")}").onFirst()
                source.assertExists(); reveal(source); shot("05b-saved-answer-sources")
                phase.optString("saved_asset_id").takeIf { it.isNotBlank() }?.let { asset ->
                    readAction("saved_voice_read") { model.playSavedSpeech(id, asset) }
                    verifyPlayback("answer:$id", "06-saved-voice", exerciseControls = true)
                    result.put("saved_answer_played", true).put("saved_asset_id", asset); persist()
                }
                if(phase.optBoolean("play_saved_answer_voice", false)) {
                    assertTrue("Use only a previously enabled voice profile", model.ui.value.voiceProfile.optBoolean("ready"))
                    val attempts = File(activity.filesDir, "cloud-twin-attempts").apply { mkdirs() }
                    // Share the existing guard with new-answer speech; never remove an old attempt.
                    val speechMarker = File(attempts, "$runId-$role-speech.json")
                    assertTrue("A speech generation attempt already exists for this role/run_id", speechMarker.createNewFile())
                    speechMarker.writeText(JSONObject().put("answer_id", id).put("at", Instant.now().toString()).toString())
                    result.put("new_speech_attempts", 1).put("speech_answer_id", id); event("saved_answer_voice_single_submit")
                    click("听这条回答"); idle(240_000)
                    verifyPlayback("answer:$id", "06b-saved-answer-generated-voice", exerciseControls = true)
                    result.put("saved_answer_played", true); persist()
                }
            }
            if(phase.optBoolean("ask_new", false)) askOnce(phase, runId, subject)
            playOriginal(phase.getString("episode_id"))
            event("logout")
            // Leave the original playing: logout itself must stop it and remove its downloaded cache.
            logout(); result.put("logout_cache_cleared", true); shot("11-logged-out")
            result.put("status", "passed"); event("completed")
        } catch(error: Throwable) {
            failure = error
            result.put("status", "failed").put("failed_step", step)
                .put("error_type", error.javaClass.simpleName).put("error", redact(error.message.orEmpty()).take(1000))
            if(::model.isInitialized) result.put("app_error", redact(model.ui.value.error.orEmpty()).take(500))
            runCatching { shot("failure") }; persist()
            throw error
        } finally {
            if(::model.isInitialized && model.ui.value.actor.isNotBlank()) {
                // Cleanup cannot ask again or mask the original provider/assertion failure.
                runCatching { logout(); result.put("logout_cache_cleared", true) }.onFailure { cleanup ->
                    result.put("cleanup_error", redact(cleanup.message.orEmpty()).take(500))
                    failure?.addSuppressed(cleanup)
                }
            }
            persist(); scenario.close(); password = ""; token = ""
        }
    }

    private fun askOnce(phase: JSONObject, runId: String, subject: String) {
        assertTrue("Persona requires the owner's enabled style", model.ui.value.narrative.optJSONObject("style")?.optBoolean("enabled") == true)
        click("与 AI 分身聊聊"); ui.onNodeWithText("与 AI 分身聊聊").assertIsSelected()
        val question = phase.getString("question").trim()
        ui.onNodeWithText("想了解什么？").performScrollTo().performTextReplacement(question)
        val consent = hasText(CLOUD) and isToggleable()
        ui.onNode(consent).performScrollTo().assertIsOff(); click(consent); ui.onNode(consent).assertIsOn()
        shot("07-persona-question-consented")
        // Durable guard survives test reruns/restarts; a timeout or failed model call is never retried.
        val attempts = File(activity.filesDir, "cloud-twin-attempts").apply { mkdirs() }
        val marker = File(attempts, "$runId-$role-question.json")
        assertTrue("This role/run_id already attempted a cloud question. Inspect its result; do not auto-retry.", marker.createNewFile())
        marker.writeText(JSONObject().put("run_id", runId).put("role", role).put("subject_id", subject)
            .put("question", question).put("at", Instant.now().toString()).toString(2))
        val previousAnswerId = model.ui.value.answer?.text("answer_id")
        val previousOperation = model.ui.value.operation.id
        result.put("question", question).put("new_question_attempts", 1); event("new_question_single_submit")
        click("提问")
        assertTrue("The one question click must start an operation; never retry an ignored/busy submission", model.ui.value.operation.id > previousOperation)
        ui.waitUntil(240_000) { !model.ui.value.busy && (model.ui.value.answer != null || model.ui.value.error != null) }
        idle()
        val answer = checkNotNull(model.ui.value.answer) { "No answer from the one cloud submission" }
        result.put("new_answer", answerRecord(answer)); persist()
        assertNotEquals("The displayed answer must come from this submission", previousAnswerId, answer.text("answer_id"))
        assertEquals(question, answer.text("question")); verifyAnswer(answer, subject, requirePersona = true)
        val persisted = get("/api/v1/subjects/${segment(subject)}/twin/answers/${segment(answer.text("answer_id"))}")
        assertEquals(answer.text("answer"), persisted.text("answer")); verifyAnswer(persisted, subject, requirePersona = true)
        result.put("answer_api_readback", true)
        reveal(ui.onNodeWithText(answer.text("answer"))); shot("08-new-persona-answer")
        click("查看理解与来源")
        val evidence = answer.rows("evidence").first()
        val source = ui.onAllNodesWithText("依据：${evidence.text("excerpt")}").onFirst()
        source.assertExists(); reveal(source); shot("09-answer-sources")
        if(phase.optBoolean("play_new_answer_voice", false)) {
            assertTrue("Use only a previously enabled voice profile", model.ui.value.voiceProfile.optBoolean("ready"))
            val speechMarker = File(attempts, "$runId-$role-speech.json")
            assertTrue("A speech generation attempt already exists for this role/run_id", speechMarker.createNewFile())
            speechMarker.writeText(JSONObject().put("answer_id", answer.text("answer_id")).put("at", Instant.now().toString()).toString())
            result.put("new_speech_attempts", 1); event("new_answer_voice_single_submit")
            click("听这条回答"); idle(240_000)
            verifyPlayback("answer:${answer.text("answer_id")}", "10-new-answer-voice", exerciseControls = true)
            result.put("new_answer_played", true)
        }
        persist()
    }

    private fun verifyAnswer(answer: JSONObject, subject: String, requirePersona: Boolean) {
        assertTrue("A persisted answer ID is required", answer.text("answer_id").isNotBlank())
        assertEquals(subject, answer.text("subject_id")); assertFalse("Stale answer is not valid acceptance", answer.optBoolean("stale", true))
        if(requirePersona) assertEquals("persona", answer.text("mode"))
        assertEquals("Expected an evidence-backed AI answer, not UNKNOWN", "SIMULATION", answer.text("response_type"))
        assertTrue(answer.text("answer").isNotBlank()); assertTrue(answer.text("model_version").isNotBlank())
        assertTrue(answer.text("source_version").isNotBlank()); assertTrue(answer.rows("evidence").isNotEmpty())
        answer.rows("evidence").forEach {
            assertTrue(it.text("evidence_id").isNotBlank()); assertTrue(it.text("episode_id").isNotBlank())
            assertTrue(it.text("excerpt").isNotBlank()); assertTrue(it.text("source_type").isNotBlank())
        }
    }
    private fun answerRecord(answer: JSONObject) = JSONObject().apply {
        listOf("answer_id", "subject_id", "question", "answer", "mode", "response_type", "model_version", "prompt_version",
            "person_model_version", "source_version", "created_at", "stale", "understanding_ids", "contribution_ids", "coverage", "evidence")
            .forEach { put(it, answer.opt(it) ?: JSONObject.NULL) }
    }
    private fun verifyPlayback(id: String, screenshot: String, exerciseControls: Boolean) {
        ui.waitUntil(30_000) { model.ui.value.error != null || (model.ui.value.player.episode == id && model.ui.value.player.playing && model.ui.value.player.position >= 1000) }
        idle(); assertEquals(id, model.ui.value.player.episode); assertTrue(model.ui.value.player.playing)
        assertTrue("Playback must have a real duration", model.ui.value.player.duration > 1000)
        val played = model.ui.value.player
        event("playback_verified", JSONObject().put("source", id).put("duration_ms", played.duration).put("position_ms", played.position))
        shot(screenshot)
        if(exerciseControls) {
            click(hasContentDescription("暂停")); assertFalse(model.ui.value.player.playing)
            ui.onNodeWithContentDescription("播放进度").performSemanticsAction(SemanticsActions.SetProgress) { assertTrue(it(0f)) }
            assertTrue("Seek to start must move the real player", model.ui.value.player.position < 1000)
            click(hasContentDescription("继续播放"))
            ui.waitUntil(15_000) { model.ui.value.player.playing && model.ui.value.player.position >= 500 }
            click(hasContentDescription("停止播放")); assertTrue(model.ui.value.player.episode.isBlank())
            assertTrue(File(activity.cacheDir, "native-source-audio").listFiles().orEmpty().isEmpty())
        }
    }
    private fun playOriginal(episode: String) {
        val story = model.ui.value.stories.single { it.text("episode_id") == episode }
        assertFalse("Original must be accessible to this role", story.optBoolean("unavailable"))
        event("original_ui_playback")
        click("档案"); click("全部录音"); idle()
        val siblings = hasAnySibling(hasText(storyTitle(story)))
        click(hasText("打开故事") and siblings)
        click("播放完整原音"); idle()
        verifyPlayback(episode, "10b-original-playing", exerciseControls = false)
        result.put("source_played", true).put("source_episode_id", episode); persist()
    }
    companion object {
        private const val SERVER = "https://39.108.183.47"
        private const val STYLE = "允许分身使用已确认的理解与表达"
        private const val CLOUD = "同意将问题与已授权的核对文字交由云端回答"
    }
}
