package me.remember.app.integration

import me.remember.app.data.repository.AudioRecording
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest

class ClientTranscriptTest {
    @Test fun boundedImportRejectsLargeStreamsBeforeParsing() {
        assertEquals(3, byteArrayOf(1,2,3).inputStream().readBytesLimited(3).size)
        assertThrows(IllegalArgumentException::class.java) { ByteArray(8193).inputStream().readBytesLimited(8192) }
    }
    @Test fun attemptedUploadKeepsItsRouteWhenServerProviderChanges() {
        val file=File.createTempFile("route-audio", ".m4a").apply { writeText("original") }
        try {
            val draft=ClientTranscript.parse(json(hash(file.readBytes())).toString())
            val recording=AudioRecording(file.absolutePath,1000,"audio/mp4",file.length(),44100,1,"2026-10-09T00:00:00Z")
            val capture=LocalCapture(recording,"stable").withTranscript(draft)
            assertTrue(capture.beginUpload(true).usesClientTranscript(false))
            assertFalse(capture.beginUpload(false).usesClientTranscript(true))
            // Read the first version of our persisted client-only attempted captures.
            assertTrue(capture.copy(uploadAttempted=true).usesClientTranscript(false))
        } finally { file.delete() }
    }
    private fun hash(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    private fun json(checksum: String) = JSONObject().put("text", "我先把年份记作2010年，仍需核对。")
        .put("audio_sha256", checksum).put("provider", "groq").put("model", "whisper-large-v3")
        .put("audio_export_confirmed", true)
    @Test fun acceptsActualToolEnvelopeAndPreservesMachineText() {
        val audio = File.createTempFile("asr-audio", ".m4a").apply { writeBytes(byteArrayOf(1,2,3)) }
        try {
            val source=json(hash(audio.readBytes()))
            val parsed=ClientTranscript.parse(JSONObject().put("client_transcript",source).put("human_listening",false).toString())
            parsed.requireMatches(audio)
            assertEquals(source.getString("text"),parsed.text)
            assertEquals(source.toString(),parsed.toJson().toString())
            assertEquals(parsed,ClientTranscript.parse(parsed.toJson().toString()))
        } finally { audio.delete() }
    }
    @Test fun rejectsWrongAudioUnknownProviderUnconsentedAndOversizedDrafts() {
        val audio=File.createTempFile("asr-audio", ".m4a").apply { writeText("original") }
        try {
            val valid=json(hash(audio.readBytes()))
            assertThrows(IllegalArgumentException::class.java) { ClientTranscript.parse(valid.toString()).requireMatches(File.createTempFile("different", ".m4a").apply { deleteOnExit();writeText("other") }) }
            listOf(valid.toString().replace("groq","other"), JSONObject(valid.toString()).put("audio_export_confirmed",false).toString(),
                JSONObject(valid.toString()).put("audio_export_confirmed","true").toString(),
                JSONObject(valid.toString()).put("text"," ").toString(),
                JSONObject(valid.toString()).put("text","字".repeat(100001)).toString(),
                JSONObject(valid.toString()).put("answer","not ASR").toString()).forEach { bad ->
                assertThrows(IllegalArgumentException::class.java) { ClientTranscript.parse(bad) }
            }
        } finally { audio.delete() }
    }
    @Test fun draftCannotBeReplacedAfterAnUploadAttemptOrReceivedEpisode() {
        val audio=File.createTempFile("asr-audio", ".m4a").apply { writeText("original") }
        try {
            val recording=AudioRecording(audio.absolutePath,1000,"audio/mp4",audio.length(),44100,1,"2026-10-09T00:00:00Z")
            val draft=ClientTranscript.parse(json(hash(audio.readBytes())).toString())
            val original=LocalCapture(recording,"stable").withTranscript(draft)
            assertEquals(draft,original.transcript)
            assertThrows(IllegalArgumentException::class.java) { original.copy(uploadAttempted=true).withTranscript(draft) }
            assertThrows(IllegalArgumentException::class.java) { original.copy(episode="received").withTranscript(draft) }
        } finally { audio.delete() }
    }
}
