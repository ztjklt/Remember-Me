package me.remember.app

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import me.remember.app.data.local.*
import me.remember.app.data.repository.AgentRepository
import me.remember.app.data.repository.AudioRecording

enum class CaptureProgress { IDLE, RUNNING, PAUSED, FAILED, COMPLETE }

data class LocalSessionState(val ready: Boolean = false, val busy: Boolean = false, val localMode: Boolean = true,
    val captureProgress: CaptureProgress = CaptureProgress.IDLE, val error: String? = null, val message: String? = null, val pending: Boolean = false, val checkpoint: String? = null)

/** Activity-independent operations; interrupted jobs remain durable for explicit resume after restart. */
class LocalAgentSession(application: Application) : AndroidViewModel(application) {
    private val mutableState = MutableStateFlow(LocalSessionState())
    val state: StateFlow<LocalSessionState> = mutableState
    private val preferences = application.getSharedPreferences("execution-mode", 0)
    private val secrets = LocalSettingsStore(application)
    private val client = HttpLocalModelClient()
    private val library = RecordingLibrary(java.io.File(application.filesDir, "recordings"))
    private val keeper = MemoryKeeper(application)
    var reminder by mutableStateOf(keeper.settings())
        private set
    fun reminderAllowed() = keeper.allowed()
    fun refreshReminder() { keeper.schedule(); reminder = keeper.settings() }
    fun saveReminder(value: RecordingReminder) {
        if (!BuildConfig.LOCAL_AGENT_ENABLED || state.value.busy) return
        runCatching { keeper.save(value); reminder = keeper.settings() }
            .onSuccess { mutableState.value = mutableState.value.copy(error = null, message = getApplication<Application>().getString(R.string.reminder_saved)) }
            .onFailure { mutableState.value = mutableState.value.copy(error = it.message) }
    }
    var recordings by mutableStateOf<List<LocalRecording>>(emptyList())
        private set
    var versions by mutableStateOf<List<org.json.JSONObject>>(emptyList())
        private set
    private var engine: LocalAgentEngine? = null
    private var database: SqliteLocalState? = null
    @Volatile var settings: LocalModelSettings? = null
        private set
    var modelDraft by mutableStateOf<LocalModelSettings?>(null)
    private var lastCapture: AudioRecording? = null
    val memories: me.remember.app.data.repository.MemoryRepository? get() = engine
    var repository: AgentRepository? = null
        private set

    init {
        mutableState.value = mutableState.value.copy(localMode = BuildConfig.LOCAL_AGENT_ENABLED && preferences.getBoolean("local", true))
        if (!BuildConfig.LOCAL_AGENT_ENABLED) mutableState.value = mutableState.value.copy(ready = true)
        else viewModelScope.launch {
            try {
                withContext(Dispatchers.IO) {
                    database = SqliteLocalState(application)
                    engine = LocalAgentEngine(database!!, client) { settings }
                    try { settings = secrets.read()?.let(LocalModelSettings::from) }
                    catch (_: Exception) { mutableState.value = mutableState.value.copy(error = "模型配置无法解密，请重新填写并保存。") }
                }
                repository = AgentRepository(engine!!)
                if (engine!!.granted()) {
                    repository!!.enable(engine!!.connection())
                    restoreAnswer()
                }
                mutableState.value = mutableState.value.copy(ready = true)
                syncPending()
            } catch (e: Exception) { mutableState.value = mutableState.value.copy(error = if (e is LocalRecoveryRequired) e.message else "本地数据无法打开，请保留应用数据以便检查。") }
        }
    }
    fun setLocalMode(value: Boolean) {
        if (value && !BuildConfig.LOCAL_AGENT_ENABLED) return
        if (state.value.busy || repository?.state?.value?.busy == true) return
        preferences.edit().putBoolean("local", value).apply()
        mutableState.value = mutableState.value.copy(localMode = value)
        keeper.schedule()
    }
    fun syncPending() {
        val job = engine?.pending()
        mutableState.value = mutableState.value.copy(pending = job != null,
            captureProgress = if (job?.optString("kind") == "CAPTURE" && state.value.captureProgress == CaptureProgress.IDLE) CaptureProgress.PAUSED else state.value.captureProgress,
            checkpoint = job?.optJSONObject("evidence")?.optString("excerpt"))
    }
    fun save(config: LocalModelSettings, consent: Boolean, completed: () -> Unit) = operation {
        require(consent) { "请确认录音与模型处理同意。" }
        config.validate()
        withContext(Dispatchers.IO) { secrets.write(config.json()) }
        settings = config
        modelDraft = config
        repository!!.enable(engine!!.connection())
        check(repository!!.state.value.configured) { "本地会话启用失败。" }
        mutableState.value = mutableState.value.copy(message = "模型配置已加密保存。")
        completed()
    }
    fun test(config: LocalModelSettings, recording: AudioRecording? = null, speech: Boolean = false) = operation {
        config.validate()
        val result = if (speech) client.transcribe(checkNotNull(recording) { "请先录一段，再测试语音模型。" }, config)
        else {
            val response = client.complete("连接测试：仅输出 JSON {\"ok\":true}。", org.json.JSONObject(), config.language)
            check(response.optBoolean("ok")) { "文字模型未返回预期 JSON。" }
            "文字模型连接成功。"
        }
        mutableState.value = mutableState.value.copy(message = if (speech) "语音模型返回：$result" else result)
    }
    fun capture(recording: AudioRecording) = operation {
        lastCapture = recording
        mutableState.value = mutableState.value.copy(captureProgress = CaptureProgress.RUNNING)
        val before = repository!!.state.value.snapshot?.revision ?: 0
        engine!!.capture(recording)
        repository!!.refresh()
        check(repository!!.state.value.error == null) { "读取处理结果失败，请刷新。" }
        mutableState.value = mutableState.value.copy(captureProgress = if ((repository!!.state.value.snapshot?.revision ?: 0) > before)
            CaptureProgress.COMPLETE else CaptureProgress.IDLE, message = "原文和理解已保存在手机。")
    }
    fun retry() = operation {
        val capture = engine!!.pending()?.optString("kind") == "CAPTURE"
        val before = repository!!.state.value.snapshot?.revision ?: 0
        if (capture) mutableState.value = mutableState.value.copy(captureProgress = CaptureProgress.RUNNING)
        engine!!.retry(); repository!!.refresh(); restoreAnswer()
        if (capture) mutableState.value = mutableState.value.copy(captureProgress =
            if ((repository!!.state.value.snapshot?.revision ?: 0) > before) CaptureProgress.COMPLETE else CaptureProgress.IDLE)
    }
    fun retryCapture() { if (state.value.pending) retry() else lastCapture?.let(::capture) }
    fun cancelPending() = operation { engine!!.cancelPending(); repository!!.refresh(); mutableState.value = mutableState.value.copy(captureProgress = CaptureProgress.IDLE) }
    fun loadLibrary() = operation { refreshLibrary() }
    private suspend fun refreshLibrary() {
        recordings = withContext(Dispatchers.IO) { engine!!.recordings(library.list()) }
        versions = engine!!.versions()
    }
    fun deleteRecording(recording: AudioRecording) = operation {
        try { engine!!.deleteRecording(recording) { library.delete(recording); database!!.clearRecovery() } }
        finally {
            repository = AgentRepository(engine!!).also { if (engine!!.granted()) it.enable(engine!!.connection()) }
            lastCapture = null
            refreshLibrary()
        }
    }
    fun clearLocalData() = operation {
        engine!!.reset { library.clear(); secrets.clear(); database!!.clearRecovery() }
        keeper.clear(); reminder = keeper.settings()
        settings = null; modelDraft = null; lastCapture = null
        repository = AgentRepository(engine!!)
        recordings = emptyList(); versions = emptyList()
        preferences.edit().putBoolean("local", false).apply()
        mutableState.value = mutableState.value.copy(localMode = false, captureProgress = CaptureProgress.IDLE, message = "本地资料已清除，已退出手机模式。")
    }
    fun exportRecovery(uri: android.net.Uri) {
        if (!BuildConfig.LOCAL_AGENT_ENABLED || state.value.busy) return
        viewModelScope.launch {
            mutableState.value = mutableState.value.copy(busy = true)
            try {
                withContext(Dispatchers.IO) {
                    val text = database!!.recoveryText()
                    getApplication<Application>().contentResolver.openOutputStream(uri)?.bufferedWriter()?.use { it.write(text) }
                        ?: error("无法打开导出位置")
                }
                mutableState.value = mutableState.value.copy(message = "原文已导出；不包含模型配置。")
            } catch (_: Exception) { mutableState.value = mutableState.value.copy(message = "暂时无法导出，请保留应用数据并升级。") }
            finally { mutableState.value = mutableState.value.copy(busy = false) }
        }
    }
    private suspend fun restoreAnswer() { engine!!.latestCalibration()?.let { repository!!.resume(it) } }
    private fun operation(block: suspend () -> Unit) {
        if (!BuildConfig.LOCAL_AGENT_ENABLED || !state.value.ready || state.value.busy || repository?.state?.value?.busy == true) return
        mutableState.value = mutableState.value.copy(busy = true, error = null, message = null)
        viewModelScope.launch {
            try { block() }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) { mutableState.value = mutableState.value.copy(captureProgress = if (state.value.captureProgress == CaptureProgress.RUNNING) CaptureProgress.FAILED else state.value.captureProgress, error = when (e) {
                is IllegalArgumentException, is IllegalStateException -> e.message ?: "本地操作失败，可重试。"
                else -> "模型响应或本地存储异常，材料已保留，可重试。"
            }) }
            finally { mutableState.value = mutableState.value.copy(busy = false); syncPending() }
        }
    }
    override fun onCleared() { database?.close(); super.onCleared() }
}
