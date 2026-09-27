package me.remember.app.data.repository

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import me.remember.app.model.Loadable
import me.remember.app.model.Memory
import java.time.Instant

class LocalMemoryRepository(private val audioCaptureService: AudioCaptureService) : MemoryRepository {
    override fun memories(): Flow<Loadable<List<Memory>>> = flow {
        val values = audioCaptureService.recordings().flatMap { recording ->
            recording.memories.filter { it.status == "active" }.map { memory ->
                Memory(
                    id = memory.id,
                    date = runCatching { Instant.parse(recording.createdAt).toString().take(10) }.getOrDefault(recording.createdAt.take(10)),
                    place = "本地录音",
                    story = memory.content,
                    people = if (memory.kind == "person" || memory.kind == "relationship") listOf(memory.kind) else emptyList(),
                    tags = listOf(memory.kind),
                    duration = formatDuration(recording.durationMillis)
                )
            }
        }
        emit(if (values.isEmpty()) Loadable.Empty else Loadable.Content(values))
    }

    private fun formatDuration(durationMillis: Long): String {
        val totalSeconds = durationMillis / 1000
        return "%02d:%02d".format(totalSeconds / 60, totalSeconds % 60)
    }
}
