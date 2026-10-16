package me.remember.app.integration

import java.io.InputStream
import java.io.OutputStream

internal fun copyAudioWithProgress(input: InputStream, output: OutputStream, total: Long, progress: (Long, Long) -> Unit) {
    var sent = 0L
    progress(0, total)
    val bytes = ByteArray(64 * 1024)
    while (true) {
        val count = input.read(bytes)
        if (count < 0) break
        output.write(bytes, 0, count)
        sent += count
        progress(sent, total)
    }
}
