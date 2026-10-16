package me.remember.app.integration

import androidx.compose.material3.*
import androidx.compose.runtime.*
import org.json.JSONObject

internal fun hasRecordingHighlights(report: JSONObject?) = report!=null && (report.optInt("marker_count")>0 || report.optBoolean("device_marker_pending"))
internal fun recordingHighlightLabel(report: JSONObject?): String = when {
    report==null -> "设备重点"
    report.optInt("device_marker_count")>0 -> "设备重点 ${report.optInt("device_marker_count")}"
    report.optBoolean("device_marker_pending") -> "设备重点待定位"
    report.optInt("phone_marker_count")>0 -> "手机补充 ${report.optInt("phone_marker_count")}"
    else -> "标记详情"
}

@Composable internal fun RecordingHighlights(report: JSONObject?, edited: Boolean = false) {
    if(!hasRecordingHighlights(report) || report==null) return
    var expanded by remember(report) { mutableStateOf(false) }
    if(report.optBoolean("device_marker_pending")) Text("收到设备标记，暂未找到可靠的原音位置。",style=MaterialTheme.typography.bodyMedium)
    val points=if(report.has("markers")) report.rows("markers") else report.rows("spans").flatMap {it.rows("markers")}.distinctBy {it.toString()}
    points.filter {it.text("origin")=="device"}.take(20).forEach { point ->
        val ms=point.optLong("offset_ms")
        Text("录音豆标记 · ${markerTime(ms)}",style=MaterialTheme.typography.titleSmall)
        val spans=report.rows("spans").filter {span -> span.rows("markers").any {it.optLong("offset_ms")==ms && it.text("origin")=="device"}}
        if(spans.isEmpty() || edited) Text("时间已定位，文字待对应。",style=MaterialTheme.typography.bodyMedium)
        else spans.forEach {Text(it.text("excerpt"),style=MaterialTheme.typography.bodyMedium)}
    }
    val phone=points.filter {it.text("origin")=="phone"}
    if(phone.isNotEmpty()) TextButton(onClick={expanded=!expanded}) {Text(if(expanded) "收起手机补充" else "手机补充 ${report.optInt("phone_marker_count",phone.size)} 处")}
    if(expanded) phone.take(40).forEach {Text("手机添加 · ${markerTime(it.optLong("offset_ms"))}",style=MaterialTheme.typography.bodyMedium)}
    if(report.optInt("mapped_count")>0) Text("整理记忆时会关注已对应的重点内容。",style=MaterialTheme.typography.bodyMedium)
}

internal fun markerTime(ms:Long): String {
    return "${clock(ms)}.${(ms%1000).toString().padStart(3,'0')}"
}
