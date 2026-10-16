package me.remember.app.hardware

import java.io.File
import java.security.MessageDigest

/** Device-provided marked Opus packets, matched to the complete saved audio. */
internal object DeviceMarkerPackets {
    private fun hex(bytes:ByteArray):String = buildString(bytes.size*2) {for(b in bytes) {append("0123456789abcdef"[(b.toInt() and 255) ushr 4]);append("0123456789abcdef"[b.toInt() and 15])}}
    fun fingerprint(packet: ByteArray): String = hex(MessageDigest.getInstance("SHA-256").digest(packet))
    fun locate(raw: File, fingerprints: Set<String>, durationMs: Long): List<Long> {
        if(fingerprints.isEmpty() || raw.length()==0L || raw.length()%160!=0L || raw.length()/160*20!=durationMs) return emptyList()
        val positions=mutableMapOf<String,Long>(); val ambiguous=mutableSetOf<String>()
        val digest=MessageDigest.getInstance("SHA-256")
        raw.inputStream().buffered().use { input ->
            val packet=ByteArray(160);var offset=0L
            while(true) {
                val first=input.read();if(first<0)break;packet[0]=first.toByte()
                var read=1;while(read<160) { val n=input.read(packet,read,160-read);if(n<=0)return emptyList();read+=n }
                if(runCatching {opusPacketDurationUs(packet)}.getOrNull()!=20000L) return emptyList()
                val hash=hex(digest.digest(packet))
                if(hash in fingerprints) {if(positions.putIfAbsent(hash,offset)!=null)ambiguous.add(hash)}
                offset+=20
            }
        }
        val offsets=positions.filterKeys {it !in ambiguous}.values.sorted()
        return offsets.filterIndexed {i,ms -> i==0 || ms-offsets[i-1]>20}
    }
}
