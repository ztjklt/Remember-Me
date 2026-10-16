package me.remember.app.hardware

enum class DeviceRecordPhase { IDLE, RECORDING, PAUSED, ENDED, UNKNOWN }
data class RecorderMark(val offsetMs: Long, val origin: String) {
    init { require(offsetMs >= 0 && origin in setOf("phone", "device")) }
}

/** Device events are authoritative. Navigation and wall-clock changes never end a recording. */
class RecorderTimeline(private val now: () -> Long = { System.nanoTime() / 1_000_000 }) {
    var phase = DeviceRecordPhase.IDLE; private set
    var fileId: Int? = null; private set
    private var milliseconds = 0L
    private var observedAt = now()
    private val pending = linkedSetOf<Int>()
    private val finished = mutableSetOf<Int>()
    private var annotations = emptyList<RecorderMark>()
    val pendingFiles get() = pending.toList()
    val marks get() = annotations
    fun elapsedMs(): Long = milliseconds + if (phase == DeviceRecordPhase.RECORDING)
        (now() - observedAt).coerceIn(0, 10_000) else 0

    fun status(status: Int, durationMs: Long, id: Int) {
        if (status !in 0..2 || id <= 0 || durationMs < 0 || id in finished) return
        if (fileId != null && id < fileId!!) return
        if (id != fileId) {
            fileId = id; annotations = emptyList(); milliseconds = 0; phase = DeviceRecordPhase.IDLE
        }
        val next = when (status) { 1 -> DeviceRecordPhase.RECORDING; 2 -> DeviceRecordPhase.PAUSED; else -> DeviceRecordPhase.ENDED }
        if (next != phase || durationMs > milliseconds) {
            milliseconds = maxOf(milliseconds, durationMs)
            observedAt = now()
        }
        phase = next
        if (next == DeviceRecordPhase.ENDED) pending.add(id)
    }
    fun duration(ms: Long) {
        if (fileId == null || phase !in setOf(DeviceRecordPhase.RECORDING, DeviceRecordPhase.PAUSED) || ms < milliseconds) return
        milliseconds = ms; observedAt = now()
    }
    fun mark(offsetMs: Long, origin: String) {
        if (fileId == null || offsetMs < 0) return
        annotations = (annotations + RecorderMark(offsetMs, origin)).distinct().sortedBy { it.offsetMs }
    }
    fun completed(id: Int) { pending.remove(id); finished.add(id) }
    fun disconnected() { milliseconds = elapsedMs(); phase = DeviceRecordPhase.UNKNOWN }
}

fun transferPercent(received: Long, total: Long): Int? =
    if (total <= 0 || received < 0) null else ((received.coerceAtMost(total).toDouble() / total) * 100).toInt().coerceIn(0, 100)
