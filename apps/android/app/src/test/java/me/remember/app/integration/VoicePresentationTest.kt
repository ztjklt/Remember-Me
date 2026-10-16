package me.remember.app.integration

import org.junit.Assert.*
import org.junit.Test

class VoicePresentationTest {
    @Test fun retiredCallbacksCannotReplaceTheCurrentConversation() {
        for (kind in listOf("transcript", "error", "answer_ready", "audio", "audio_end", "turn_started", "interrupted")) {
            assertFalse(kind, acceptsVoiceEvent(kind, 3, 4, false, false))
        }
        assertTrue(acceptsVoiceEvent("transcript", 4, 4, false, false))
    }
    @Test fun localInterruptionBlocksOutputUntilTheNewTurnArrives() {
        for (kind in listOf("answer_ready", "audio", "audio_end")) {
            assertFalse(kind, acceptsVoiceEvent(kind, 4, 4, true, false))
        }
        assertTrue(acceptsVoiceEvent("interrupted", 5, 4, true, false))
        assertTrue(acceptsVoiceEvent("turn_started", 5, 5, false, false))
    }
    @Test fun pauseDoesNotAcceptLateSpeechOrOutput() {
        for (kind in listOf("transcript", "answer_ready", "audio", "audio_end")) {
            assertFalse(kind, acceptsVoiceEvent(kind, 4, 4, false, true))
        }
        assertTrue(acceptsVoiceEvent("error", 4, 4, false, true))
    }
    @Test fun playbackAcknowledgementCannotOverwriteNewSpeechOrFailure() {
        for (phase in listOf(CallPhase.THINKING, CallPhase.PAUSED, CallPhase.FAILED, CallPhase.ENDED)) {
            val state = CallUi(active = true, phase = phase, status = "new state")
            assertEquals(state, state.playbackStarted())
            assertEquals(state, state.playbackFinished())
        }
    }
    @Test fun preparingOnlyBecomesSpeakingWhenPlaybackActuallyAdvances() {
        val ready = CallUi(active = true, ready = true, phase = CallPhase.PREPARING, status = "准备播报")
        assertTrue(ready.canInterrupt)
        assertEquals(CallPhase.SPEAKING, ready.playbackStarted().phase)
        assertEquals("我在听", ready.playbackStarted().playbackFinished().status)
        assertFalse(ready.copy(paused = true).canInterrupt)
        assertFalse(ready.copy(active = false).canInterrupt)
    }
}
