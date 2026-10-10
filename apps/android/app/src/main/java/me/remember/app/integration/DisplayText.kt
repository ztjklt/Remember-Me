package me.remember.app.integration

import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

internal fun recordingDate(value: String): String = runCatching {
    OffsetDateTime.parse(value).atZoneSameInstant(ZoneId.systemDefault())
        .format(DateTimeFormatter.ofPattern("yyyy年M月d日 HH:mm"))
}.getOrDefault(value.take(16).replace('T', ' '))

internal fun processingLabel(value: String) = when(value) {
    "ready", "complete" -> "已整理"
    "captured", "uploaded", "queued" -> "已保存，等待处理"
    "transcribing" -> "正在转成文字"
    "extracting", "processing" -> "正在整理记忆"
    "reviewing" -> "待核对文字"
    "failed" -> "处理未完成"
    "pending" -> "待本人核对"
    "confirmed" -> "本人已确认"
    "rejected" -> "本人已拒绝"
    "superseded" -> "已被更新"
    else -> "状态待更新"
}
