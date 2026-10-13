package me.remember.app.integration

import kotlinx.coroutines.test.runTest
import me.remember.app.data.repository.AudioRecording
import org.junit.Assert.*
import org.junit.Test

class CaptureSubmissionTest {
    private val recording = AudioRecording("/retained/recording.m4a", 3000, "audio/mp4", 1024, 44100, 1, "2026-10-07T10:00:00Z")
    @Test fun failedRevisionLinkPersistsReceivedEpisodeAndRetryCannotReviewUntilLinked() = runTest {
        val initial = LocalCapture(recording, "stable-key", revision = RevisionTarget("old-memory", "correction", ""))
        val calls = mutableListOf<String>(); var saved = initial
        try {
            submitCapture(initial, upload = { calls += "upload"; "episode-1" },
                persist = { calls += "save:${it.linked}"; saved = it }, link = { episode, _ ->
                    assertEquals("episode-1", episode); calls += "link"; throw IllegalStateException("network unavailable")
                })
            fail("Failed link must not finish submission")
        } catch(_: IllegalStateException) { }
        assertEquals(listOf("upload", "save:false", "link"), calls)
        assertEquals("episode-1", saved.episode); assertTrue(saved.blocksReview)
        calls.clear()
        val complete = submitCapture(saved, upload = { fail("Retry must reuse received Episode"); "" },
            persist = { calls += "save:${it.linked}"; saved = it }, link = { _, _ -> calls += "link" })
        assertEquals(listOf("save:false", "link", "save:true"), calls)
        assertFalse(complete.blocksReview); assertEquals(initial.key, complete.key)
        assertEquals(recording, complete.recording)
    }
    @Test fun changeWithoutTimeFailsBeforeUpload() = runTest {
        var uploaded = false
        try {
            submitCapture(LocalCapture(recording, "key", revision = RevisionTarget("old", "change", "")),
                upload = { uploaded = true; "new" }, persist = {}, link = { _, _ -> })
            fail("Change requires explicit time context")
        } catch(_: IllegalArgumentException) { }
        assertFalse(uploaded)
    }
    @Test fun ordinaryStoryHasNoRevisionRequestAndRetainsOriginal() = runTest {
        val received = submitCapture(LocalCapture(recording, "key"), upload = { "episode" }, persist = {},
            link = { _, _ -> fail("Ordinary capture cannot link a revision") })
        assertTrue(received.linked); assertFalse(received.blocksReview); assertEquals(recording, received.recording)
    }
}
