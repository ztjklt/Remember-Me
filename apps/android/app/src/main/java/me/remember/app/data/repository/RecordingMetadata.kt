package me.remember.app.data.repository

import org.json.JSONArray
import org.json.JSONObject

/** Backward-compatible sidecars. Machine text and reviewed text are deliberately separate. */
object RecordingMetadata {
    fun recoverInterrupted(recording: AudioRecording): AudioRecording =
        if (recording.processingStage in listOf(ProcessingStage.Transcribing, ProcessingStage.Organizing))
            recording.copy(processingStage = ProcessingStage.Failed,
                processingError = "处理已中断，可重试。原音和已保存的文字仍在。")
        else recording

    fun encode(recording: AudioRecording): String = JSONObject().apply {
        put("audioPath", recording.audioPath); put("durationMillis", recording.durationMillis)
        put("mimeType", recording.mimeType); put("byteSize", recording.byteSize)
        put("sampleRate", recording.sampleRate); put("channelCount", recording.channelCount)
        put("created_at", recording.createdAt); put("title", recording.title)
        put("transcript", recording.transcript); put("summary", recording.summary)
        put("asrStatus", recording.asrStatus.name); put("personModelVersion", recording.personModelVersion)
        put("reviewedTranscript", recording.reviewedTranscript ?: JSONObject.NULL)
        put("reviewedAt", recording.reviewedAt ?: JSONObject.NULL)
        put("processingStage", recording.processingStage.name)
        put("processingError", recording.processingError ?: JSONObject.NULL)
        put("memories", JSONArray().apply { recording.memories.forEach { memory -> put(JSONObject().apply {
            put("id", memory.id); put("kind", memory.kind); put("content", memory.content)
            put("evidence", memory.evidence); put("confidence", memory.confidence.toDouble())
            put("sourceType", memory.sourceType); put("status", memory.status)
        }) } })
    }.toString()

    fun decode(text: String): AudioRecording = JSONObject(text).let { json ->
        val transcript = json.optString("transcript")
        fun optional(key: String) = if (json.isNull(key)) null else json.optString(key).takeIf { it.isNotBlank() }
        AudioRecording(
            audioPath = json.getString("audioPath"), durationMillis = json.getLong("durationMillis"),
            mimeType = json.getString("mimeType"), byteSize = json.getLong("byteSize"),
            sampleRate = json.getInt("sampleRate"), channelCount = json.getInt("channelCount"),
            createdAt = json.optString("created_at", json.optString("createdAt")),
            title = json.optString("title", "未命名录音"), transcript = transcript,
            summary = json.optString("summary"), personModelVersion = json.optString("personModelVersion"),
            asrStatus = runCatching { AsrStatus.valueOf(json.optString("asrStatus")) }.getOrDefault(AsrStatus.NotRequested),
            reviewedTranscript = optional("reviewedTranscript"), reviewedAt = optional("reviewedAt"),
            processingStage = runCatching { ProcessingStage.valueOf(json.optString("processingStage")) }
                .getOrDefault(if (transcript.isBlank()) ProcessingStage.Unprocessed else ProcessingStage.NeedsReview),
            processingError = optional("processingError"),
            memories = json.optJSONArray("memories")?.let { array -> buildList {
                for (index in 0 until array.length()) array.optJSONObject(index)?.let { item ->
                    add(ExtractedMemory(item.optString("id"), item.optString("kind"), item.optString("content"),
                        item.optString("evidence"), item.optDouble("confidence", .5).toFloat(),
                        item.optString("sourceType", "SUBJECT"), item.optString("status", "active")))
                }
            } } ?: emptyList()
        )
    }
}
