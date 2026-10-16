package me.remember.app.hardware

import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

class Work3200ImportTest {
    @get:Rule val temp = TemporaryFolder()
    private val scope = HardwareScope("https://example.invalid", "actor-a", "subject-a")
    private val recording = DeviceRecording(1700000000, 0, 160, 20, 0)

    @Test fun devicePacketEvidenceSurvivesRestartAndResolvesOnlyWithinItsAccount() {
        val root=temp.newFolder();val journal=Work3200ImportJournal(root)
        val first=ByteArray(160) {if(it==0) 0xf8.toByte() else 1}
        val second=ByteArray(160) {if(it==0) 0xf8.toByte() else 2}
        journal.recordDeviceSignal(scope,"device-a",recording.fileId,DeviceMarkerPackets.fingerprint(second))
        val raw=File(journal.rawDirectory,"packet.raw").apply {writeBytes(first+second)}
        val saved=journal.recordDownloaded(scope,"device-a",recording.copy(sizeBytes=320,durationMs=40),raw)
        val reopened=Work3200ImportJournal(root)
        assertTrue(reopened.deviceMarkerPending(saved.importId,scope))
        val marks=reopened.resolveDevicePackets(saved.importId,scope,40)
        assertEquals(listOf(RecorderMark(20,"device")),marks)
        reopened.saveMarkers(scope,"device-a",recording.fileId,marks)
        assertFalse(reopened.deviceMarkerPending(saved.importId,scope))
        reject {reopened.resolveDevicePackets(saved.importId,scope.copy(actorId="another"),40)}
    }

    @Test fun markersBeforeAndAfterDownloadSurviveRestartAndStayScoped() {
        val root = temp.newFolder()
        val journal = Work3200ImportJournal(root)
        journal.saveMarkers(scope, "device-a", recording.fileId, listOf(RecorderMark(10, "phone")))
        val raw = File(journal.rawDirectory, "marks.raw").apply { writeBytes(ByteArray(160)) }
        val saved = journal.recordDownloaded(scope, "device-a", recording, raw)
        journal.saveMarkers(scope, "device-a", recording.fileId, listOf(RecorderMark(10, "device"), RecorderMark(10, "device")))
        val reopened = Work3200ImportJournal(root)
        assertEquals(2, reopened.markers(saved.importId, scope).size)
        assertTrue(reopened.markers(scope.copy(actorId = "other"), "device-a", recording.fileId).isEmpty())
        reject { reopened.markers(saved.importId, scope.copy(actorId = "other")) }
    }

    @Test fun uploadedDerivativeCanBeReusedButNotReplaced() {
        val journal = Work3200ImportJournal(temp.newFolder())
        val raw = File(journal.rawDirectory, "replay.raw").apply { writeBytes(ByteArray(160)) }
        val saved = journal.recordDownloaded(scope, "device-a", recording, raw)
        val prepared = File(journal.preparedDirectory, "replay.wav").apply { writeBytes(wav()) }
        journal.prepare(saved.importId, scope, prepared, "fixture")
        journal.markUploaded(saved.importId, scope, "episode")
        assertEquals("episode", journal.prepare(saved.importId, scope, prepared, "fixture").episodeId)
        prepared.appendBytes(byteArrayOf(1))
        reject { journal.prepare(saved.importId, scope, prepared, "fixture") }
    }

    @Test fun downloadReceiptsSurviveRestartAndEnforceScopeAndChecksum() {
        val root = temp.newFolder()
        val journal = Work3200ImportJournal(root)
        val raw = File(journal.rawDirectory, "retained.raw").apply { writeBytes(ByteArray(160) { 7 }) }
        val saved = journal.recordDownloaded(scope, "device-a", recording, raw)
        val reopened = Work3200ImportJournal(root)
        assertEquals(160L, reopened.downloaded(scope).single().bytes)
        assertTrue(reopened.downloaded(scope.copy(actorId = "other")).isEmpty())
        reject { reopened.rawReceipt(saved.importId, scope.copy(actorId = "other")) }
        raw.writeBytes(ByteArray(160) { 8 })
        reject { reopened.rawReceipt(saved.importId, scope) }
        assertTrue(reopened.downloaded(scope).isEmpty())
    }

    private fun wav(): ByteArray = ByteBuffer.allocate(684).order(ByteOrder.LITTLE_ENDIAN).apply {
        put("RIFF".toByteArray()); putInt(676); put("WAVEfmt ".toByteArray()); putInt(16)
        putShort(1); putShort(1); putInt(16000); putInt(32000); putShort(2); putShort(16)
        put("data".toByteArray()); putInt(640); put(ByteArray(640))
    }.array()

    private fun reject(block: () -> Unit) {
        try { block(); fail("Unsafe input was accepted") } catch (_: IllegalArgumentException) { }
    }

    @Test fun rawOpusRenamedWavCannotBecomeUploadCandidate() {
        val journal = Work3200ImportJournal(temp.newFolder())
        val raw = File(journal.rawDirectory, "recording.opus").apply { writeBytes(ByteArray(160) { 17 }) }
        val entry = journal.recordDownloaded(scope, "device-a", recording, raw)
        val fake = File(journal.preparedDirectory, "fake.wav").apply { writeBytes(raw.readBytes()) }
        reject { journal.prepare(entry.importId, scope, fake, "not-a-decoder") }
        reject { journal.uploadCandidate(entry.importId, scope) }
        assertTrue(raw.exists())
    }

    @Test fun importRetryAfterRestartKeepsIdempotencyAndEpisode() {
        val root = temp.newFolder()
        var journal = Work3200ImportJournal(root)
        val raw = File(journal.rawDirectory, "recording.opus").apply { writeBytes(ByteArray(160) { 17 }) }
        val entry = journal.recordDownloaded(scope, "device-a", recording, raw)
        val prepared = File(journal.preparedDirectory, "derived.wav").apply { writeBytes(wav()) }
        journal.prepare(entry.importId, scope, prepared, "fixture-only")
        journal.markUploaded(entry.importId, scope, "episode-a")
        journal = Work3200ImportJournal(root)
        val retry = journal.recordDownloaded(scope, "device-a", recording, raw)
        assertEquals(entry.idempotencyKey, retry.idempotencyKey)
        assertEquals("episode-a", retry.episodeId)
        val upload = journal.uploadCandidate(retry.importId, scope)
        assertEquals("WORK_3200", upload.source)
        assertEquals(20L, upload.audio.durationMs)
        assertEquals(16000, upload.audio.sampleRate)
        assertEquals(1, upload.audio.channels)
        assertEquals("episode-a", upload.episodeId)
        reject { journal.markUploaded(entry.importId, scope, "episode-b") }
        assertEquals(160L, raw.length())
    }

    @Test fun sameDeviceFileCannotBeReusedForDifferentBytesAndScopesDoNotCollide() {
        val journal = Work3200ImportJournal(temp.newFolder())
        val raw = File(journal.rawDirectory, "a.opus").apply { writeBytes(ByteArray(160) { 1 }) }
        val first = journal.recordDownloaded(scope, "device-a", recording, raw)
        val second = journal.recordDownloaded(scope.copy(subjectId = "subject-b"), "device-a", recording, raw)
        assertNotEquals(first.idempotencyKey, second.idempotencyKey)
        raw.writeBytes(ByteArray(160) { 2 })
        reject { journal.recordDownloaded(scope, "device-a", recording, raw) }
    }

    @Test fun traversalAndFilesOutsidePrivateDirectoriesAreRejected() {
        val journal = Work3200ImportJournal(temp.newFolder())
        val raw = File(journal.rawDirectory, "a.opus").apply { writeBytes(ByteArray(160)) }
        listOf("../other", "..", "a/b", "a\\b", "C:evil").forEach { key ->
            reject { journal.recordDownloaded(scope, key, recording, raw) }
        }
        reject { journal.recordDownloaded(scope, "device-a", recording, temp.newFile()) }
        reject { journal.uploadCandidate("../outside", scope) }
        reject { DeviceRecording(-1, 0, 10, 20, 0) }
    }

    @Test fun changedPreparedOrRawFileCannotBeUploaded() {
        val journal = Work3200ImportJournal(temp.newFolder())
        val raw = File(journal.rawDirectory, "a.opus").apply { writeBytes(ByteArray(160)) }
        val entry = journal.recordDownloaded(scope, "device-a", recording, raw)
        val prepared = File(journal.preparedDirectory, "a.wav").apply { writeBytes(wav()) }
        journal.prepare(entry.importId, scope, prepared, "fixture-only")
        prepared.appendBytes(byteArrayOf(1))
        reject { journal.uploadCandidate(entry.importId, scope) }
        prepared.writeBytes(wav()); raw.writeBytes(ByteArray(160) { 3 })
        reject { journal.uploadCandidate(entry.importId, scope) }
    }

    @Test fun wavValidationRejectsTruncationAndInconsistentPcmHeader() {
        val file = temp.newFile("audio.wav")
        file.writeBytes(wav().dropLast(1).toByteArray())
        reject { Work3200Audio.inspectPcmWav(file) }
        val bad = wav(); bad[32] = 4
        file.writeBytes(bad)
        reject { Work3200Audio.inspectPcmWav(file) }
    }

    @Test fun anotherAccountCannotPrepareReadOrAttachAnEpisodeToRetainedImport() {
        val journal = Work3200ImportJournal(temp.newFolder())
        val raw = File(journal.rawDirectory, "a.opus").apply { writeBytes(ByteArray(160)) }
        val entry = journal.recordDownloaded(scope, "device-a", recording, raw)
        val prepared = File(journal.preparedDirectory, "a.wav").apply { writeBytes(wav()) }
        val other = scope.copy(actorId = "actor-b")
        reject { journal.prepare(entry.importId, other, prepared, "fixture-only") }
        journal.prepare(entry.importId, scope, prepared, "fixture-only")
        reject { journal.uploadCandidate(entry.importId, other) }
        reject { journal.markUploaded(entry.importId, other, "wrong-episode") }
        assertNull(journal.uploadCandidate(entry.importId, scope).episodeId)
    }
}
