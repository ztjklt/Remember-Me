package me.remember.app.data.local

import me.remember.app.data.repository.AudioRecording
import org.json.JSONObject
import java.io.File
import java.time.Instant

/** Only app-owned audio and its matching sidecar may be removed. */
class RecordingLibrary(private val root: File) {
    fun list(): List<AudioRecording> = root.listFiles { f -> f.extension == "m4a" && f.isFile }?.map { file ->
        val metadata = runCatching { JSONObject(File(root, file.nameWithoutExtension + ".json").readText()) }.getOrNull()
        AudioRecording(file.absolutePath, metadata?.optLong("durationMillis") ?: 0, "audio/mp4", file.length(),
            metadata?.optInt("sampleRate") ?: 44100, metadata?.optInt("channelCount") ?: 1,
            metadata?.optString("created_at")?.takeIf { it.isNotBlank() } ?: Instant.ofEpochMilli(file.lastModified()).toString())
    }.orEmpty().sortedByDescending { it.createdAt }
    fun delete(recording: AudioRecording) {
        val file = File(recording.audioPath)
        require(file.canonicalFile.parentFile == root.canonicalFile && file.extension == "m4a") { "拒绝删除录音目录以外的文件。" }
        val sidecar = File(root, file.nameWithoutExtension + ".json")
        require(sidecar.canonicalFile.parentFile == root.canonicalFile)
        check(!file.exists() || file.delete()) { "录音文件删除失败，请重试。" }
        check(!sidecar.exists() || sidecar.delete()) { "录音信息删除失败，请重试。" }
    }
    fun clear() {
        list().forEach(::delete)
        root.listFiles { f -> f.extension == "json" }?.forEach {
            require(it.canonicalFile.parentFile == root.canonicalFile)
            check(it.delete()) { "录音信息删除失败。" }
        }
    }
}
data class LocalRecording(val recording: AudioRecording, val excerpt: String, val status: String)
