package me.remember.app

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import me.remember.app.data.local.*
import me.remember.app.data.repository.AgentRepository
import me.remember.app.data.repository.AudioRecording

data class LocalSessionState(val ready: Boolean = false, val busy: Boolean = false, val localMode: Boolean = true,
    val error: String? = null, val message: String? = null, val pending: Boolean = false, val checkpoint: String? = null)

/** Activity-independent operations; interrupted jobs remain durable for explicit resume after restart. */
class LocalAgentSession(application: Application) : AndroidViewModel(application) {
    private val mutableState = MutableStateFlow(LocalSessionState())
    val state: StateFlow<LocalSessionState> = mutableState
    private val preferences = application.getSharedPreferences("execution-mode", 0)
    private val secrets = LocalSettingsStore(application)
    private val client = HttpLocalModelClient()
    private var engine: LocalAgentEngine? = null
    private var database: SqliteLocalState? = null
    @Volatile var settings: LocalModelSettings? = null
        private set
    var repository: AgentRepository? = null
        private set

    init {
        mutableState.value = mutableState.value.copy(localMode = preferences.getBoolean("local", true))
        viewModelScope.launch {
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
            } catch (_: Exception) { mutableState.value = mutableState.value.copy(error = "本地数据无法打开，请保留应用数据以便检查。") }
        }
    }
    fun setLocalMode(value: Boolean) {
        if (state.value.busy || repository?.state?.value?.busy == true) return
        preferences.edit().putBoolean("local", value).apply()
        mutableState.value = mutableState.value.copy(localMode = value)
    }
    fun syncPending() {
        val job = engine?.pending()
        mutableState.value = mutableState.value.copy(pending = job != null,
            checkpoint = job?.optJSONObject("evidence")?.optString("excerpt"))
    }
    fun save(config: LocalModelSettings, consent: Boolean, completed: () -> Unit) = operation {
        require(consent) { "请确认录音与模型处理同意。" }
        config.validate()
        withContext(Dispatchers.IO) { secrets.write(config.json()) }
        settings = config
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
        engine!!.capture(recording)
        repository!!.refresh()
        mutableState.value = mutableState.value.copy(message = "原文和理解已保存在手机。")
    }
    fun retry() = operation { engine!!.retry(); repository!!.refresh(); restoreAnswer() }
    fun cancelPending() = operation { engine!!.cancelPending() }
    private suspend fun restoreAnswer() { engine!!.latestCalibration()?.let { repository!!.resume(it) } }
    private fun operation(block: suspend () -> Unit) {
        if (!state.value.ready || state.value.busy || repository?.state?.value?.busy == true) return
        mutableState.value = mutableState.value.copy(busy = true, error = null, message = null)
        viewModelScope.launch {
            try { block() }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) { mutableState.value = mutableState.value.copy(error = when (e) {
                is IllegalArgumentException, is IllegalStateException -> e.message ?: "本地操作失败，可重试。"
                else -> "模型响应或本地存储异常，材料已保留，可重试。"
            }) }
            finally { mutableState.value = mutableState.value.copy(busy = false); syncPending() }
        }
    }
    override fun onCleared() { database?.close(); super.onCleared() }
}
