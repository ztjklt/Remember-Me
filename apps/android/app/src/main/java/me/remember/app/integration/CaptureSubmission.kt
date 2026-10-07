package me.remember.app.integration

import me.remember.app.data.repository.AudioRecording

data class RevisionTarget(val memory: String, val kind: String, val time: String)
data class LocalCapture(val recording: AudioRecording, val key: String, val episode: String = "", val revision: RevisionTarget? = null, val linked: Boolean = false) {
    val blocksReview get() = revision != null && !linked
}

/** Journal the Episode before linking: a failed link retries that Episode, never a new recording. */
suspend fun submitCapture(
    capture: LocalCapture,
    upload: suspend () -> String,
    persist: suspend (LocalCapture) -> Unit,
    link: suspend (String, RevisionTarget) -> Unit
): LocalCapture {
    capture.revision?.let {
        require(it.memory.isNotBlank() && it.kind in setOf("supplement", "correction", "change")) { "修订关系无效。" }
        require(it.kind != "change" || it.time.isNotBlank()) { "请说明情况变化的大致时间。" }
    }
    val episode = capture.episode.ifBlank { upload() }
    val received = capture.copy(episode = episode)
    persist(received)
    received.revision?.let { link(episode, it) }
    return received.copy(linked = true).also { persist(it) }
}
