package me.remember.app.integration

import me.remember.app.data.repository.AudioRecording
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.net.ServerSocket
import java.util.concurrent.Executors
import java.security.MessageDigest
import org.json.JSONObject

class BackendClientTest {
    @Test fun readingAttributedOriginalUsesOnlyReadEndpointWithoutModelPermission() {
        val errors=mutableListOf<Throwable>();val requests=mutableListOf<String>()
        val server=TinyServer(1,errors) {headers,body ->
            requests+=headers.getValue(":request-line")
            assertEquals("Bearer reader",headers["authorization"]);assertEquals("",body)
            ok("{\"id\":\"note-one\",\"text\":\"亲友原文\",\"author_display_name\":\"亲友\",\"model_use_author_allowed\":false,\"model_use_owner_allowed\":false}")
        }
        server.use {
            val gate=SessionGate();val session=gate.connect(server.url,"reader")
            val original=BackendClient(gate).companionOriginal(session,"subject","note-one")
            assertEquals("亲友原文",original.text("text"));assertFalse(contributionModelUseAllowed(original))
        }
        assertTrue(errors.toString(),errors.isEmpty())
        assertEquals(listOf("GET /api/v1/workbench/subjects/subject/companion/contributions/note-one HTTP/1.1"),requests)
    }
    @Test fun realHttpUsesBearerNoCacheAndDoesNotFollowRedirect() {
        val errors = mutableListOf<Throwable>()
        val server = TinyServer(1, errors) { headers, _ ->
            assertEquals("Bearer owner-token", headers["authorization"])
            assertEquals("no-store", headers["cache-control"])
            "HTTP/1.1 302 Found\r\nLocation: /api/v1/stolen\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        }
        server.use {
            val gate = SessionGate(); val s = gate.connect(server.url, "owner-token")
            assertThrows(IllegalStateException::class.java) { BackendClient(gate).json(s, "/api/v1/workbench/spaces") }
        }
        assertTrue(errors.toString(), errors.isEmpty())
    }
    @Test fun lateResponseRejectedAfterIdentityChanges() {
        val gate = SessionGate()
        val server = TinyServer(1, mutableListOf()) { _, _ -> gate.clear(); ok("{\"actor_id\":\"former-owner\"}") }
        server.use {
            val s = gate.connect(server.url, "owner")
            assertThrows(IllegalStateException::class.java) { BackendClient(gate).json(s, "/api/v1/workbench/spaces") }
        }
    }
    @Test fun uploadRetainsOriginalAndStableRetryKeyWithAndroidProvenance() {
        val file = File.createTempFile("capture", ".m4a").apply { writeBytes(byteArrayOf(0, 1, 2, 3)) }
        val bodies = mutableListOf<String>(); val errors = mutableListOf<Throwable>()
        val server = TinyServer(2, errors) { _, body -> bodies += body; ok("{\"episode_id\":\"episode-1\"}") }
        try {
            server.use {
                val gate = SessionGate(); val s = gate.connect(server.url, "owner")
                val client = BackendClient(gate)
                val recording = AudioRecording(file.absolutePath, 1000, "audio/mp4", 4, 44100, 1, "2026-10-07T12:00:00Z")
                repeat(2) { assertEquals("episode-1", client.upload(s, "subject", "consent", recording, "same-retry-key")) }
                assertTrue(file.isFile)
            }
            assertTrue(errors.toString(), errors.isEmpty()); assertEquals(2, bodies.size)
            bodies.forEach { body ->
                assertTrue(body.contains("ANDROID_MIC")); assertTrue(body.contains("same-retry-key"))
                assertTrue(body.contains("name=\"recording_consent_id\"")); assertTrue(body.contains("Content-Type: audio/mp4"))
                assertFalse(body.contains(file.absolutePath))
            }
        } finally { file.delete() }
    }
    @Test fun clientDraftUsesNewEndpointWithoutLosingAndroidSourceOrRetryIdentity() {
        val file=File.createTempFile("capture", ".m4a").apply { writeText("retained original") }
        val checksum=MessageDigest.getInstance("SHA-256").digest(file.readBytes()).joinToString("") { "%02x".format(it) }
        val draft=ClientTranscript.parse(JSONObject().put("text","原始机器稿，不等于已核对。")
            .put("audio_sha256",checksum).put("provider","groq").put("model","whisper-large-v3")
            .put("audio_export_confirmed",true).toString())
        val errors=mutableListOf<Throwable>(); val bodies=mutableListOf<String>(); val requests=mutableListOf<Map<String,String>>()
        val server=TinyServer(2,errors) { headers,body ->
            requests+=headers; bodies+=body;ok("{\"episode_id\":\"ep-client\"}")
        }
        try {
            server.use {
                val gate=SessionGate();val session=gate.connect(server.url,"owner")
                val recording=AudioRecording(file.absolutePath,1000,"audio/mp4",file.length(),44100,1,"2026-10-09T00:00:00Z")
                repeat(2) { assertEquals("ep-client",BackendClient(gate).upload(session,"subject","consent",recording,"stable-key",transcript=draft)) }
            }
            assertTrue(errors.toString(),errors.isEmpty())
            requests.forEach { assertEquals("POST /api/v1/episodes/client-transcribed HTTP/1.1",it[":request-line"]); assertEquals("Bearer owner",it["authorization"]) }
            bodies.forEach { assertTrue(it.contains("ANDROID_MIC"));assertTrue(it.contains("name=\"client_transcript\""));assertTrue(it.contains(checksum));assertTrue(it.contains("stable-key"));assertFalse(it.contains("reviewed_at")) }
            assertEquals("retained original",file.readText())
        } finally { file.delete() }
    }
    @Test fun work3200UploadKeepsHardwareSourceConsentAndOriginalBytesAcrossRetries() {
        val file=File.createTempFile("decoded-device", ".wav").apply {writeText("decoded hardware audio fixture")}
        val errors=mutableListOf<Throwable>();val bodies=mutableListOf<String>()
        val server=TinyServer(2,errors) {headers,body ->
            assertEquals("POST /api/v1/episodes HTTP/1.1",headers[":request-line"])
            assertEquals("Bearer owner",headers["authorization"])
            bodies+=body;ok("{\"episode_id\":\"device-episode\"}")
        }
        try {
            server.use {
                val gate=SessionGate();val session=gate.connect(server.url,"owner")
                val recording=AudioRecording(file.absolutePath,2500,"audio/wav",file.length(),16000,1,"2026-10-13T00:00:00Z")
                repeat(2) {assertEquals("device-episode",BackendClient(gate).upload(session,"subject","explicit-consent",recording,"same-device-key","agreed-policy",source="WORK_3200"))}
            }
            assertTrue(errors.toString(),errors.isEmpty());assertEquals(2,bodies.size)
            bodies.forEach {body ->
                assertTrue(body.contains("name=\"source\"\r\n\r\nWORK_3200"))
                assertTrue(body.contains("name=\"recording_consent_id\"\r\n\r\nexplicit-consent"))
                assertTrue(body.contains("\"cloud_asr_policy\":\"agreed-policy\""))
                assertTrue(body.contains("same-device-key"));assertTrue(body.contains("Content-Type: audio/wav"))
                assertTrue(body.contains("decoded hardware audio fixture"));assertFalse(body.contains(file.absolutePath))
            }
            assertEquals("decoded hardware audio fixture",file.readText())
        } finally {file.delete()}
    }
    @Test fun companionAudioIsDedicatedMultipartWithStableRetryIdentity() {
        val file=File.createTempFile("companion", ".m4a").apply {writeText("dedicated audio")}
        val errors=mutableListOf<Throwable>();val bodies=mutableListOf<String>()
        val server=TinyServer(2,errors) {headers,body ->
            assertEquals("POST /api/v1/workbench/subjects/subject/companion/audio HTTP/1.1",headers[":request-line"])
            assertEquals("Bearer contributor",headers["authorization"])
            bodies+=body;ok("{\"audio_id\":\"dedicated\",\"status\":\"saved\",\"revision\":1}")
        }
        try {
            server.use {
                val gate=SessionGate();val session=gate.connect(server.url,"contributor")
                repeat(2) {assertEquals("dedicated",BackendClient(gate).uploadCompanionAudio(session,"subject","contribution",file,"audio/mp4","same-key").text("audio_id"))}
            }
            assertTrue(errors.toString(),errors.isEmpty());assertEquals(2,bodies.size)
            bodies.forEach {body ->
                assertTrue(body.contains("name=\"purpose\"\r\n\r\ncontribution"));assertTrue(body.contains("name=\"file\""));assertTrue(body.contains("same-key"))
                assertFalse(body.contains("episode_id"));assertFalse(body.contains("recording_consent_id"));assertFalse(body.contains(file.absolutePath))
            }
            assertTrue(file.exists())
        } finally {file.delete()}
    }
    @Test fun calibrationImportRetainsAudioAndLockedAnswerLinkAcrossRetries() {
        val file=File.createTempFile("calibration", ".wav").apply {writeText("original human audio")}
        val errors=mutableListOf<Throwable>();val bodies=mutableListOf<String>()
        val server=TinyServer(2,errors) {headers,body ->
            assertEquals("POST /api/v1/episodes HTTP/1.1",headers[":request-line"])
            bodies+=body;ok("{\"episode_id\":\"human-episode\"}")
        }
        try {
            server.use {
                val gate=SessionGate();val session=gate.connect(server.url,"owner")
                val recording=AudioRecording(file.absolutePath,2500,"audio/wav",file.length(),24000,1,"2026-10-12T00:00:00Z")
                repeat(2) {assertEquals("human-episode",BackendClient(gate).upload(session,"subject","consent",recording,"stable-calibration","agreed-policy",calibrationId="locked-answer-run",source="IMPORT"))}
            }
            assertTrue(errors.toString(),errors.isEmpty());assertEquals(2,bodies.size)
            bodies.forEach {body ->
                assertTrue(body.contains("\"calibration_id\":\"locked-answer-run\""))
                assertTrue(body.contains("name=\"source\"\r\n\r\nIMPORT"))
                assertTrue(body.contains("Content-Type: audio/wav"));assertTrue(body.contains("stable-calibration"))
                assertTrue(body.contains("original human audio"));assertFalse(body.contains("client_transcript"))
            }
            assertEquals("original human audio",file.readText())
        } finally {file.delete()}
    }
    private fun ok(body: String): String = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ${body.toByteArray().size}\r\nConnection: close\r\n\r\n$body"
    /** Exercise real HTTP without introducing a mocked networking stack. */
    private class TinyServer(count: Int, errors: MutableList<Throwable>, handler: (Map<String,String>, String) -> String) : AutoCloseable {
        private val socket = ServerSocket(0)
        private val executor = Executors.newSingleThreadExecutor()
        private val task = executor.submit {
            repeat(count) {
                try { socket.accept().use { client ->
                    client.soTimeout = 10_000
                    val input = client.getInputStream().buffered()
                    fun line(): String {
                        val value = StringBuilder()
                        while(true) { val b = input.read(); if(b < 0 || b == 10) break; if(b != 13) value.append(b.toChar()) }
                        return value.toString()
                    }
                    val requestLine = line()
                    val headers = mutableMapOf<String,String>()
                    headers[":request-line"] = requestLine
                    while(true) { val row = line(); if(row.isEmpty()) break; val split = row.indexOf(':'); headers[row.substring(0, split).lowercase()] = row.substring(split + 1).trim() }
                    val body = java.io.ByteArrayOutputStream()
                    if(headers["transfer-encoding"] == "chunked") {
                        while(true) {
                            val length = line().substringBefore(';').toInt(16)
                            if(length == 0) { line(); break }
                            repeat(length) { body.write(input.read()) }; line()
                        }
                    } else repeat(headers["content-length"]?.toInt() ?: 0) { body.write(input.read()) }
                    client.getOutputStream().write(handler(headers, body.toString("UTF-8")).toByteArray())
                } } catch(error: Throwable) { errors.add(error) }
            }
        }
        val url get() = "http://127.0.0.1:${socket.localPort}"
        override fun close() {
            try { task.get(15, java.util.concurrent.TimeUnit.SECONDS) }
            finally { socket.close(); executor.shutdownNow() }
        }
    }
}
