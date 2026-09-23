package me.remember.app.feature

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class CaptureStateTest {
    @Test
    fun recordingCanPauseResumeAndSave() {
        val state = CaptureState.Idle
            .then(CaptureEvent.BeginStart)
            .then(CaptureEvent.Start)
            .then(CaptureEvent.Pause)
            .then(CaptureEvent.Resume)
            .then(CaptureEvent.Save)

        assertEquals(CaptureState.Saved, state)
    }

    @Test
    fun pausedRecordingCanBeSaved() {
        val state = CaptureState.Idle
            .then(CaptureEvent.BeginStart)
            .then(CaptureEvent.Start)
            .then(CaptureEvent.Pause)
            .then(CaptureEvent.Save)

        assertEquals(CaptureState.Saved, state)
    }

    @Test
    fun deniedPermissionCanBeRetried() {
        val state = CaptureState.Idle
            .then(CaptureEvent.DenyPermission)
            .then(CaptureEvent.Reset)
            .then(CaptureEvent.BeginStart)
            .then(CaptureEvent.Start)

        assertEquals(CaptureState.Recording, state)
    }

    @Test
    fun recorderFailureCanBeRetried() {
        val state = CaptureState.Idle
            .then(CaptureEvent.BeginStart)
            .then(CaptureEvent.Start)
            .then(CaptureEvent.Fail)
            .then(CaptureEvent.BeginStart)
            .then(CaptureEvent.Start)

        assertEquals(CaptureState.Recording, state)
    }

    @Test
    fun repeatedStartFailureRemainsRecoverable() {
        val state = CaptureState.Idle
            .then(CaptureEvent.BeginStart)
            .then(CaptureEvent.Start)
            .then(CaptureEvent.Fail)
            .then(CaptureEvent.BeginStart)
            .then(CaptureEvent.Start)
            .then(CaptureEvent.Fail)

        assertEquals(CaptureState.Failed, state)
    }

    @Test
    fun cannotResumeWithoutPausedRecording() {
        assertThrows(IllegalStateException::class.java) {
            reduceCaptureState(CaptureState.Recording, CaptureEvent.Resume)
        }
    }

    @Test
    fun cannotStartAgainWhileMicrophoneIsStarting() {
        val starting = reduceCaptureState(CaptureState.Idle, CaptureEvent.BeginStart)
        assertThrows(IllegalStateException::class.java) {
            reduceCaptureState(starting, CaptureEvent.BeginStart)
        }
        assertEquals(CaptureState.Failed, reduceCaptureState(starting, CaptureEvent.Fail))
    }

    @Test
    fun cannotSaveWithoutActiveRecording() {
        assertThrows(IllegalStateException::class.java) {
            reduceCaptureState(CaptureState.Idle, CaptureEvent.Save)
        }
    }

    private fun CaptureState.then(event: CaptureEvent) = reduceCaptureState(this, event)
}
