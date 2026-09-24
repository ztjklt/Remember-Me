package me.remember.app.data.repository

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

sealed interface EpisodeUiState {
    data object Idle : EpisodeUiState
    data class Uploading(val percent: Int) : EpisodeUiState
    data class Processing(val episodeId: String, val stage: EpisodeStage) : EpisodeUiState
    data class Ready(val episodeId: String, val memoryCount: Int) : EpisodeUiState
    data class Error(
        val episodeId: String?,
        val code: String,
        val message: String,
        val retryable: Boolean
    ) : EpisodeUiState
}

/** One capture at a time. The Episode id survives status retries in this app session. */
class EpisodeFlow(
    private val gateway: EpisodeGateway,
    private val memories: EpisodeMemoryRepository,
    private val pollIntervalMillis: Long = 1_500L,
    private val maxStatusChecks: Int = 80
) {
    private val mutableState = MutableStateFlow<EpisodeUiState>(EpisodeUiState.Idle)
    val state: StateFlow<EpisodeUiState> = mutableState

    private var recording: AudioRecording? = null
    private var connection: BackendConnection? = null
    private var episodeId: String? = null
    private var running = false

    suspend fun submit(recording: AudioRecording, connection: BackendConnection) {
        if (running) return
        this.recording = recording
        this.connection = connection
        episodeId = null
        memories.clear()
        runPending()
    }

    suspend fun retry() {
        if (running || mutableState.value !is EpisodeUiState.Error) return
        if ((mutableState.value as EpisodeUiState.Error).retryable) runPending()
    }

    private suspend fun runPending() {
        val savedRecording = recording ?: return
        val settings = connection ?: return
        running = true
        try {
            if (episodeId == null) {
                mutableState.value = EpisodeUiState.Uploading(0)
                val created = gateway.upload(savedRecording, settings) { percent ->
                    mutableState.value = EpisodeUiState.Uploading(percent.coerceIn(0, 100))
                }
                episodeId = created.episodeId
            }
            val id = checkNotNull(episodeId)
            repeat(maxStatusChecks) {
                val status = gateway.status(id, settings)
                when (status.stage) {
                    EpisodeStage.FAILED -> {
                        mutableState.value = EpisodeUiState.Error(
                            id,
                            status.errorCode ?: "PROCESSING_FAILED",
                            status.errorMessage ?: "处理失败，原始录音仍保存在此设备。",
                            false
                        )
                        return
                    }
                    EpisodeStage.READY -> {
                        try {
                            val result = gateway.result(id, settings)
                            memories.show(result)
                            mutableState.value = EpisodeUiState.Ready(id, result.memories.size)
                            return
                        } catch (error: EpisodeGatewayFailure) {
                            if (error.code != "EPISODE_NOT_READY") throw error
                        }
                    }
                    else -> mutableState.value = EpisodeUiState.Processing(id, status.stage)
                }
                delay(pollIntervalMillis)
            }
            mutableState.value = EpisodeUiState.Error(
                id,
                "STATUS_TIMEOUT",
                "处理仍未完成。请确认 Backend worker 正在运行，再继续查询状态。",
                true
            )
        } catch (error: CancellationException) {
            throw error
        } catch (error: EpisodeGatewayFailure) {
            mutableState.value = EpisodeUiState.Error(
                episodeId,
                error.code,
                error.message,
                error.retryable
            )
        } finally {
            running = false
        }
    }
}
