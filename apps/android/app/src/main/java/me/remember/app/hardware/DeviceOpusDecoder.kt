package me.remember.app.hardware

import android.media.AudioFormat
import android.media.MediaCodec
import android.media.MediaFormat
import android.os.SystemClock
import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.UUID

/** Vendor 1.3.02 guide: 160-byte raw Opus packets, 20 ms, two channels.
 * Rejects other framing; real device format still requires physical acceptance.
 * Android MediaCodec's Opus output is read from the reported PCM format (usually 48 kHz).
 */
object DeviceOpusDecoder {
    fun decode(raw: File, target: File, progress: (Long, Long) -> Unit = { _, _ -> }): File {
        if (target.isFile) { Work3200Audio.inspectPcmWav(target); return target }
        require(raw.length() in 160L..(8L * 1024 * 1024) && raw.length() % 160 == 0L) { "Unsupported raw framing" }
        val pending = File(target.parentFile, "${UUID.randomUUID()}.pending")
        val codec = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_AUDIO_OPUS)
        var started = false
        try {
            val header = ByteBuffer.allocate(19).order(ByteOrder.LITTLE_ENDIAN).apply {
                put("OpusHead".toByteArray()); put(1); put(2); putShort(0); putInt(16000); putShort(0); put(0); flip()
            }
            val format = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_OPUS, 48000, 2).apply {
                setByteBuffer("csd-0", header)
                setByteBuffer("csd-1", ByteBuffer.allocate(8).order(ByteOrder.nativeOrder()).putLong(0).apply { flip() })
                setByteBuffer("csd-2", ByteBuffer.allocate(8).order(ByteOrder.nativeOrder()).putLong(80_000_000).apply { flip() })
                setInteger(MediaFormat.KEY_PCM_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
            }
            codec.configure(format, null, null, 0); codec.start(); started = true
            var frames = 0L; var inputEnd = false; var outputEnd = false; var rate = 0; var channels = 0
            val info = MediaCodec.BufferInfo()
            val stopAt = SystemClock.elapsedRealtime() + 120_000
            RandomAccessFile(pending, "rw").use { wav ->
                wav.write(ByteArray(44))
                raw.inputStream().buffered().use { input ->
                    while (!outputEnd) {
                        require(SystemClock.elapsedRealtime() < stopAt && !Thread.currentThread().isInterrupted) { "Decoder timeout" }
                        if (!inputEnd) {
                            val slot = codec.dequeueInputBuffer(10_000)
                            if (slot >= 0) {
                                val packet = ByteArray(160)
                                var count = 0
                                while (count < packet.size) { val n = input.read(packet, count, packet.size - count); if (n < 0) break; count += n }
                                if (count == 0) { codec.queueInputBuffer(slot, 0, 0, frames * 20_000, MediaCodec.BUFFER_FLAG_END_OF_STREAM); inputEnd = true }
                                else {
                                    require(count == 160 && opusPacketDurationUs(packet) == 20_000L) { "Unexpected Opus packet duration" }
                                    codec.getInputBuffer(slot)!!.apply { clear(); put(packet) }
                                    codec.queueInputBuffer(slot, 0, packet.size, frames * 20_000, 0); frames++
                                    if (frames % 25 == 0L) progress(frames * 160, raw.length())
                                }
                            }
                        }
                        val slot = codec.dequeueOutputBuffer(info, 10_000)
                        if (slot == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                            val output = codec.outputFormat
                            rate = output.getInteger(MediaFormat.KEY_SAMPLE_RATE); channels = output.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
                            require(channels == 2 && rate in setOf(16000, 48000))
                            require(!output.containsKey(MediaFormat.KEY_PCM_ENCODING) || output.getInteger(MediaFormat.KEY_PCM_ENCODING) == AudioFormat.ENCODING_PCM_16BIT)
                        } else if (slot >= 0) {
                            try {
                                if (info.size > 0 && info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG == 0) {
                                    require(rate > 0 && wav.length() + info.size < 100L * 1024 * 1024)
                                    val buffer = codec.getOutputBuffer(slot)!!.apply { position(info.offset); limit(info.offset + info.size) }
                                    val bytes = ByteArray(info.size); buffer.get(bytes); wav.write(bytes)
                                }
                                outputEnd = info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0
                            } finally { codec.releaseOutputBuffer(slot, false) }
                        }
                    }
                }
                val size = wav.length().toInt() - 44
                require(size > 0 && rate > 0 && channels == 2)
                val duration = size * 1000L / (rate * channels * 2)
                require(kotlin.math.abs(duration - frames * 20) <= 40) { "Decoded duration does not match received packets" }
                val wavHeader = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN).apply {
                    put("RIFF".toByteArray()); putInt(size + 36); put("WAVEfmt ".toByteArray()); putInt(16)
                    putShort(1); putShort(channels.toShort()); putInt(rate); putInt(rate * channels * 2)
                    putShort((channels * 2).toShort()); putShort(16); put("data".toByteArray()); putInt(size)
                }.array()
                wav.seek(0); wav.write(wavHeader); wav.fd.sync()
            }
            Work3200Audio.inspectPcmWav(pending)
            Files.move(pending.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE)
            return target
        } finally {
            if (started) runCatching { codec.stop() }
            codec.release(); pending.delete()
        }
    }
}

/** Opus TOC duration, per RFC 6716 section 3; no invented packet boundaries. */
internal fun opusPacketDurationUs(packet: ByteArray): Long {
    require(packet.size >= 2)
    val toc = packet[0].toInt() and 255; val config = toc shr 3
    val perFrame = when {
        config >= 16 -> 2500L shl (config and 3)
        config >= 12 -> 10000L shl (config and 1)
        config and 3 == 3 -> 60000L
        else -> 10000L shl (config and 3)
    }
    val frames = when (toc and 3) { 0 -> 1; 1, 2 -> 2; else -> packet[1].toInt() and 63 }
    require(frames > 0 && perFrame * frames <= 120_000)
    return perFrame * frames
}
