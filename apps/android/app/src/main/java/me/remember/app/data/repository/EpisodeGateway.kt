package me.remember.app.data.repository

import me.remember.app.model.Memory

data class BackendConnection(
    val baseUrl: String,
    val actorToken: String,
    val subjectId: String,
    val recordingConsentId: String,
    val subjectSingleSpeaker: Boolean = false
)

data class EpisodeCreated(val episodeId: String, val uploadStatus: String)

enum class EpisodeStage {
    UPLOADED, TRANSCRIBING, EXTRACTING, MODELING, READY, FAILED
}

data class EpisodeStatus(
    val episodeId: String,
    val stage: EpisodeStage,
    val errorCode: String? = null,
    val errorMessage: String? = null
)

data class EpisodeResult(
    val episodeId: String,
    val modelVersion: String,
    val memories: List<Memory>
)

interface EpisodeGateway {
    suspend fun upload(
        recording: AudioRecording,
        connection: BackendConnection,
        onProgress: (Int) -> Unit
    ): EpisodeCreated

    suspend fun status(episodeId: String, connection: BackendConnection): EpisodeStatus

    suspend fun result(episodeId: String, connection: BackendConnection): EpisodeResult
}

class EpisodeGatewayFailure(
    val code: String,
    override val message: String,
    val retryable: Boolean
) : Exception(message)
