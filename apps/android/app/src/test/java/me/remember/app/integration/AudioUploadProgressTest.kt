package me.remember.app.integration

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.OutputStream

class AudioUploadProgressTest {
    @Test fun progressCountsOnlySuccessfullyWrittenAudioBytes() {
        val bytes = ByteArray(150000) { (it % 127).toByte() }
        val output = ByteArrayOutputStream()
        val progress = mutableListOf<Long>()
        copyAudioWithProgress(ByteArrayInputStream(bytes), output, bytes.size.toLong()) { sent, total ->
            assertEquals(150000L, total); progress.add(sent)
        }
        assertArrayEquals(bytes, output.toByteArray())
        assertEquals(0L, progress.first())
        assertEquals(150000L, progress.last())
        assertTrue(progress.zipWithNext().all { it.first <= it.second })
    }
    @Test fun failedWriteNeverReportsComplete() {
        val progress = mutableListOf<Long>()
        val output = object : OutputStream() { override fun write(b: Int) { throw IOException("offline") } }
        try {
            copyAudioWithProgress(ByteArrayInputStream(ByteArray(100)), output, 100) { sent, _ -> progress.add(sent) }
            fail("write must fail")
        } catch (_: IOException) { }
        assertEquals(listOf(0L), progress)
    }
}
