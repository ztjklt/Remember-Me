package me.remember.app.hardware

import org.junit.Assert.*
import org.junit.Test

class RecorderTimelineTest {
    @Test fun longRecordingPauseAndAnonymousResumeExcludePausedTime() {
        var now = 0L
        val timeline = RecorderTimeline { now }
        assertFalse(timeline.status(1, 0, -1))
        timeline.status(1, 0, 1000)
        now = 45000
        timeline.status(2, 0, -1)
        now = 75000
        assertEquals(45000, timeline.elapsedMs())
        assertTrue(timeline.status(1, 0, -1))
        now = 100000
        assertEquals(70000, timeline.elapsedMs())
        timeline.status(0, 69000, -1)
        timeline.reconcileDuration(2000, 9000)
        assertEquals(69000, timeline.elapsedMs())
        timeline.reconcileDuration(1000, 69500)
        assertEquals(69500, timeline.elapsedMs())
    }
    @Test fun finalDeviceDurationReplacesInterpolatedPauseEstimate() {
        var now = 0L
        val timeline = RecorderTimeline { now }
        timeline.status(1, -1, 1000)
        timeline.duration(1000)
        now += 5000
        timeline.status(2, -1, -1)
        assertEquals(6000, timeline.elapsedMs())
        timeline.status(0, 2000, -1)
        assertEquals(2000, timeline.elapsedMs())
    }
    @Test fun sdkPauseAndStopWithoutIdReferOnlyToKnownActiveRecording() {
        var now = 0L
        val timeline = RecorderTimeline { now }
        assertFalse(timeline.status(0, 2000, -1))
        assertTrue(timeline.status(1, -1, 1000)) // duration is undefined outside STOP
        timeline.duration(1200)
        now += 300
        assertTrue(timeline.status(2, -1, -1))
        assertEquals(DeviceRecordPhase.PAUSED, timeline.phase)
        assertEquals(1500, timeline.elapsedMs())
        assertTrue(timeline.status(1, -1, -1)) // Actual SDK resume callback has no file ID.
        assertTrue(timeline.status(0, 2500, -1))
        assertEquals(DeviceRecordPhase.ENDED, timeline.phase)
        assertEquals(listOf(1000), timeline.pendingFiles)
        assertEquals(2500, timeline.elapsedMs())
        assertFalse(timeline.status(0, 2500, -1))
    }
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
        timeline.duration(2500)
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
        timeline.duration(1000)
        now = 60000
        assertEquals(61000, timeline.elapsedMs()) // Known recording keeps counting beyond ten seconds.
        timeline.disconnected()
        now += 60000
        assertEquals(61000, timeline.elapsedMs()) // Only loss of known recording state freezes it.
        assertNull(transferPercent(20, 0))
        assertEquals(25, transferPercent(1, 4))
        assertEquals(100, transferPercent(6, 4))
    }
}
