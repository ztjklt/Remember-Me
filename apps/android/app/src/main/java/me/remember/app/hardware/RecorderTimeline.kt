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
        (now() - observedAt).coerceAtLeast(0) else 0

    fun status(status: Int, durationMs: Long, reportedId: Int): Boolean {
        if (status !in 0..2 || (status == 0 && durationMs < 0)) return false
        // Actual 1.3.02 resume, pause and stop callbacks may all report -1.
        // Associate those events only with an observed active recording, never
        // guess from the newest file in storage or an unknown disconnected state.
        val id = reportedId.takeIf { it > 0 } ?: if (
            phase in setOf(DeviceRecordPhase.RECORDING, DeviceRecordPhase.PAUSED)) fileId ?: return false else return false
        if (id in finished || id in pending) return false
        if (fileId != null && id < fileId!!) return false
        val measured = if (status == 0) durationMs else if (id == fileId) elapsedMs() else 0L
        if (id != fileId) {
            fileId = id; annotations = emptyList(); milliseconds = 0; phase = DeviceRecordPhase.IDLE
        }
        val next = when (status) { 1 -> DeviceRecordPhase.RECORDING; 2 -> DeviceRecordPhase.PAUSED; else -> DeviceRecordPhase.ENDED }
        if (next != phase || measured > milliseconds) {
            milliseconds = if (status == 0) measured else maxOf(milliseconds, measured)
            observedAt = now()
        }
        phase = next
        if (next == DeviceRecordPhase.ENDED) pending.add(id)
        return true
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
    fun reconcileDuration(id: Int, durationMs: Long) {
        if (id == fileId && phase == DeviceRecordPhase.ENDED && durationMs > 0) milliseconds = durationMs
    }
    fun disconnected() { milliseconds = elapsedMs(); phase = DeviceRecordPhase.UNKNOWN }
}

fun transferPercent(received: Long, total: Long): Int? =
    if (total <= 0 || received < 0) null else ((received.coerceAtMost(total).toDouble() / total) * 100).toInt().coerceIn(0, 100)
