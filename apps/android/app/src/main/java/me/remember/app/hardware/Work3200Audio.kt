package me.remember.app.hardware

import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

data class PreparedHardwareAudio(val mimeType: String, val sampleRate: Int, val channels: Int, val durationMs: Long, val byteSize: Long)

/** This is a bounded PCM WAV validator, not a raw Opus decoder. */
object Work3200Audio {
    fun inspectPcmWav(file: File): PreparedHardwareAudio {
        require(file.isFile && file.length() in 44L..(100L * 1024 * 1024)) { "Expected a bounded, complete PCM WAV file" }
        RandomAccessFile(file, "r").use { input ->
            fun ascii(length: Int) = ByteArray(length).also { input.readFully(it) }.toString(Charsets.US_ASCII)
            fun uint() = Integer.toUnsignedLong(Integer.reverseBytes(input.readInt()))
            require(ascii(4) == "RIFF" && uint() + 8 == input.length() && ascii(4) == "WAVE") { "Raw Opus and renamed files are not PCM WAV" }
            var rate = 0; var channels = 0; var dataSize = 0L; var foundData = false
            while (input.filePointer < input.length()) {
                require(input.length() - input.filePointer >= 8) { "Truncated WAV chunk" }
                val tag = ascii(4); val size = uint(); val begin = input.filePointer
                require(size <= input.length() - begin) { "Truncated WAV payload" }
                when (tag) {
                    "fmt " -> {
                        require(rate == 0 && size >= 16 && size <= 64) { "Unsupported WAV format chunk" }
                        val data = ByteArray(16); input.readFully(data)
                        val fields = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN)
                        require(fields.short.toInt() == 1) { "Only PCM WAV is accepted" }
                        channels = fields.short.toInt(); rate = fields.int
                        val bytesPerSecond = fields.int; val align = fields.short.toInt(); val bits = fields.short.toInt()
                        require(channels in 1..2 && rate in 8000..96000 && bits == 16 && align == channels * 2 && bytesPerSecond == rate * align) { "Inconsistent PCM format" }
                    }
                    "data" -> { require(!foundData && size > 0); foundData = true; dataSize = size }
                }
                val next = begin + size + size % 2
                require(next <= input.length()) { "Missing WAV chunk padding" }
                input.seek(next)
            }
            require(rate > 0 && foundData && dataSize % (channels * 2) == 0L) { "Missing or incomplete PCM audio" }
            val duration = dataSize * 1000 / (rate * channels * 2)
            require(duration > 0)
            return PreparedHardwareAudio("audio/wav", rate, channels, duration, file.length())
        }
    }
}
