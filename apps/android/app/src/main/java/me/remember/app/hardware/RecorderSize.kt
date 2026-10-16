package me.remember.app.hardware

import java.util.Locale

/** Display decimal MB; retain raw SDK byte/KB values in diagnostics. SDK KB = 1024 bytes. */
fun recorderMegabytes(bytes: Long?): String = when {
    bytes == null || bytes < 0 -> "未知"
    bytes in 1..999 -> "<0.001 MB"
    else -> String.format(Locale.ROOT, "%.3f MB", bytes / 1_000_000.0)
}
fun recorderKilobytesAsMb(kb: Int?): String = recorderMegabytes(kb?.takeIf { it >= 0 }?.toLong()?.times(1024))
