package me.remember.app.integration

import me.remember.app.data.repository.AudioRecording
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.net.ServerSocket
import java.util.concurrent.Executors

class BackendClientTest {
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
                    line()
                    val headers = mutableMapOf<String,String>()
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
        override fun close() { task.get(15, java.util.concurrent.TimeUnit.SECONDS); socket.close(); executor.shutdownNow() }
    }
}
