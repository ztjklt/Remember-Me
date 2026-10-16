package me.remember.app.hardware

import org.junit.Assert.*
import org.junit.Test

class DeviceOpusPacketTest {
    @Test fun recognizesTwentyMillisecondFramesAndRejectsEmptyFrameCount() {
        assertEquals(20_000L, opusPacketDurationUs(byteArrayOf((19 shl 3).toByte(), 0)))
        assertEquals(20_000L, opusPacketDurationUs(byteArrayOf(((18 shl 3) or 1).toByte(), 0)))
        assertThrows(IllegalArgumentException::class.java) { opusPacketDurationUs(byteArrayOf(3, 0)) }
    }
    @Test fun doesNotConfuseTenAndSixtyMillisecondPacketsWithTwenty() {
        assertEquals(10_000L, opusPacketDurationUs(byteArrayOf(0, 0)))
        assertEquals(60_000L, opusPacketDurationUs(byteArrayOf(24, 0)))
    }
}
