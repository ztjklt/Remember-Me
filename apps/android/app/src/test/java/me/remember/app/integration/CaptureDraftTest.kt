package me.remember.app.integration

import me.remember.app.data.repository.AudioRecording
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class CaptureDraftTest {
    @Test fun userEditsRoundTripWithoutReplacingMachineOrInitialText() {
        val server=JSONObject().put("transcript","修订文字").put("machine_transcript","原始字形")
            .put("recording_highlights",JSONObject().put("marker_count",2))
        val draft=CaptureDraft.fromReview("ep-a",server).copy(text="本人补正",supplement="发生在秋天")
        val restored=CaptureDraft.restore(JSONObject(draft.json().toString()))
        assertEquals("本人补正",restored.text); assertEquals("发生在秋天",restored.supplement)
        assertEquals("修订文字",restored.initial); assertEquals("原始字形",restored.machine)
        assertEquals(2,restored.highlights!!.getInt("marker_count"))
    }
    @Test fun legacyAndStillRecordingCapturesNeverUploadAutomatically() {
        val audio=AudioRecording("/retained/a.wav",25000,"audio/wav",1000,16000,1,"2026-10-16T00:00:00Z")
        val legacy=LocalCapture(audio,"a")
        assertFalse(legacy.needsAutomaticUpload())
        assertTrue(legacy.copy(autoProcess=true).needsAutomaticUpload())
        assertFalse(legacy.copy(autoProcess=true,linked=true,episode="ep-a").needsAutomaticUpload())
        assertFalse(legacy.copy(autoProcess=true,recording=audio.copy(durationMillis=0)).needsAutomaticUpload())
    }
    @Test fun newRecordingDoesNotInterruptPlaybackButAccessLossDoes() {
        val state=NativeState(player=SourcePlayback(episode="ep-a",playing=true))
        val a=JSONObject().put("episode_id","ep-a")
        assertFalse(state.playerAccessLost(listOf(a,JSONObject().put("episode_id","ep-b"))))
        assertTrue(state.playerAccessLost(listOf(a.put("unavailable",true))))
        assertTrue(state.playerAccessLost(emptyList()))
    }
}
