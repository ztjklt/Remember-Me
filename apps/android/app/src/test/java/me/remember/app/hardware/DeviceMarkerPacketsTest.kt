package me.remember.app.hardware

import org.junit.Assert.*
import org.junit.Test
import java.io.File

class DeviceMarkerPacketsTest {
    private fun packet(seed: Int)=ByteArray(160) { if(it==0) 0xf8.toByte() else seed.toByte() }
    private fun locate(packets: List<ByteArray>, marked: List<ByteArray>, duration: Long=packets.size*20L): List<Long> {
        val f=File.createTempFile("marker-packets", ".raw")
        return try { f.writeBytes(packets.fold(byteArrayOf()) { a,p -> a+p });
            DeviceMarkerPackets.locate(f,marked.map(DeviceMarkerPackets::fingerprint).toSet(),duration) } finally { f.delete() }
    }
    @Test fun markedPacketIsLocatedByActualAudioNotCallbackArrivalTimeOrSequenceGuess() {
        assertEquals(listOf(40L),locate(listOf(packet(1),packet(2),packet(3),packet(4)),listOf(packet(3))))
    }
    @Test fun contiguousMarkedFramesAreOneRegionAndRetransmissionsAreDeduplicated() {
        assertEquals(listOf(20L,80L),locate((1..6).map(::packet),listOf(packet(2),packet(3),packet(5),packet(2))))
    }
    @Test fun missingOrRepeatedAudioCannotInventAnOffset() {
        assertTrue(locate(listOf(packet(1),packet(2),packet(1)),listOf(packet(1),packet(9))).isEmpty())
    }
    @Test fun differentPacketFormatOrDurationCannotBeAligned() {
        assertTrue(locate(listOf(packet(1)),listOf(packet(1)),2000).isEmpty())
        assertTrue(locate(listOf(ByteArray(160)),listOf(ByteArray(160))).isEmpty())
    }
}
