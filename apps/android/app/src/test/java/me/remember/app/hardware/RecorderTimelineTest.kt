package me.remember.app.hardware

import org.junit.Assert.*
import org.junit.Test

class RecorderTimelineTest {
    @Test fun stoppedIdentityCannotBeReopenedBeforeDownload() {
        val timeline = RecorderTimeline { 0 }
        timeline.status(1, 0, 1000)
        timeline.status(0, 2000, 1000)
        timeline.status(1, 0, 1000)
        timeline.status(2, 3000, 1000)
        assertEquals(DeviceRecordPhase.ENDED, timeline.phase)
        assertEquals(2000, timeline.elapsedMs())
        timeline.disconnected()
        timeline.status(1, 0, 1000)
        assertEquals(DeviceRecordPhase.UNKNOWN, timeline.phase)
        assertEquals(listOf(1000), timeline.pendingFiles)
    }
    @Test fun physicalButtonsDriveTimerAndOneFinishedFile() {
        var now = 100L
        val timeline = RecorderTimeline { now }
        timeline.status(1, 0, 1000)
        now += 2300
        assertEquals(2300, timeline.elapsedMs())
        timeline.duration(2100)
        timeline.status(2, 2500, 1000)
        now += 10000
        assertEquals(2500, timeline.elapsedMs())
        timeline.status(1, 2500, 1000)
        now += 500
        assertEquals(3000, timeline.elapsedMs())
        timeline.status(0, 3000, 1000)
        timeline.status(0, 3000, 1000)
        assertEquals(DeviceRecordPhase.ENDED, timeline.phase)
        assertEquals(listOf(1000), timeline.pendingFiles)
        timeline.completed(1000)
        timeline.status(0, 3000, 1000)
        assertTrue(timeline.pendingFiles.isEmpty())
    }
    @Test fun oldEndCannotReplaceNewRecordingAndDisconnectIsUnknown() {
        val timeline = RecorderTimeline { 0 }
        timeline.status(1, 0, 1000)
        timeline.status(0, 2000, 1000)
        timeline.status(1, 0, 2000)
        timeline.status(0, 2000, 1000)
        assertEquals(2000, timeline.fileId)
        assertEquals(DeviceRecordPhase.RECORDING, timeline.phase)
        timeline.disconnected()
        assertEquals(DeviceRecordPhase.UNKNOWN, timeline.phase)
        assertEquals(listOf(1000), timeline.pendingFiles)
    }
    @Test fun duplicateStartDoesNotResetElapsedAndMarksHaveProvenance() {
        var now = 0L
        val timeline = RecorderTimeline { now }
        timeline.status(1, 0, 1000)
        now = 2000
        timeline.status(1, 0, 1000)
        assertEquals(2000, timeline.elapsedMs())
        timeline.mark(1200, "device")
        timeline.mark(1200, "device")
        timeline.mark(1200, "phone")
        assertEquals(2, timeline.marks.size)
        timeline.status(1, 0, 2000)
        assertTrue(timeline.marks.isEmpty())
    }
    @Test fun noInventedTimerOrPercentWhenDeviceIsUnknown() {
        var now = 0L
        val timeline = RecorderTimeline { now }
        timeline.duration(4000)
        assertEquals(0, timeline.elapsedMs())
        timeline.status(1, 1000, 1000)
        now = 60000
        assertEquals(11000, timeline.elapsedMs()) // stale events cannot keep ticking forever
        assertNull(transferPercent(20, 0))
        assertEquals(25, transferPercent(1, 4))
        assertEquals(100, transferPercent(6, 4))
    }
}
