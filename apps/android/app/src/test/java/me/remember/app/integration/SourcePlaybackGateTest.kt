package me.remember.app.integration

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class SourcePlaybackGateTest {
    @Test fun delayedDownloadCannotRecreateCacheOrPlayerAfterBackground() = runTest {
        val sessions = SessionGate(); val session = sessions.connect("http://127.0.0.1:8877", "owner")
        val playback = SourcePlaybackGate(sessions)
        val ticket = playback.begin(session)
        val response = CompletableDeferred<ByteArray>()
        var cachedFiles = 0; var players = 0
        launch {
            response.await()
            playback.publish(ticket) { cachedFiles++; players++ }
        }
        runCurrent()
        playback.setForeground(false)
        response.complete(byteArrayOf(1, 2, 3))
        advanceUntilIdle()
        assertEquals(0, cachedFiles); assertEquals(0, players)
        playback.setForeground(true)
        assertFalse("Returning to foreground must not revive the old download", playback.isCurrent(ticket))
    }
    @Test fun preparedCallbackCannotAutoplayAfterStopOrIdentitySwitch() {
        val sessions = SessionGate(); val session = sessions.connect("http://127.0.0.1:8877", "owner")
        val playback = SourcePlaybackGate(sessions)
        val stopped = playback.begin(session)
        playback.invalidate()
        assertFalse(playback.isCurrent(stopped))
        val oldIdentity = playback.begin(session)
        sessions.connect("http://127.0.0.1:8877", "reader")
        assertFalse(playback.isCurrent(oldIdentity))
    }
    @Test fun onlyLatestForegroundRequestCanPublish() {
        val sessions = SessionGate(); val session = sessions.connect("http://127.0.0.1:8877", "owner")
        val playback = SourcePlaybackGate(sessions)
        val old = playback.begin(session); val current = playback.begin(session)
        assertFalse(playback.isCurrent(old)); assertTrue(playback.isCurrent(current))
        var publications = 0
        assertTrue(playback.publish(current) { publications++ }); assertEquals(1, publications)
        playback.setForeground(false)
        assertThrows(IllegalStateException::class.java) { playback.begin(session) }
    }
}
