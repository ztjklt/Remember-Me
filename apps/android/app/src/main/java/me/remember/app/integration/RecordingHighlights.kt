package me.remember.app.integration

import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.text.style.TextOverflow
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
    if(report.optBoolean("device_marker_pending")) Text("设备重点待定位",style=MaterialTheme.typography.bodyLarge)
    val points=if(report.has("markers")) report.rows("markers") else report.rows("spans").flatMap {it.rows("markers")}.distinctBy {it.toString()}
    points.filter {it.text("origin")=="device"}.take(20).forEach { point ->
        val ms=point.optLong("offset_ms")
        Text("${markerTime(ms)} · 附近文字",style=MaterialTheme.typography.titleMedium)
        val spans=report.rows("spans").filter {span -> span.rows("markers").any {it.optLong("offset_ms")==ms && it.text("origin")=="device"}}
        if(spans.isEmpty() || edited) Text(if(edited) "文字已修改，保存后重新对应。" else "时间已定位，文字暂未对应。",style=MaterialTheme.typography.bodyLarge)
        else {
            val excerpt=spans.map {it.text("excerpt")}.distinct().joinToString("\n")
            var all by remember(report,ms) {mutableStateOf(false)}
            var clipped by remember(report,ms) {mutableStateOf(false)}
            Text(excerpt,style=MaterialTheme.typography.bodyLarge,maxLines=if(all) Int.MAX_VALUE else 6,
                overflow=TextOverflow.Ellipsis,onTextLayout={if(!all) clipped=it.hasVisualOverflow})
            if(clipped || all) TextButton(onClick={all=!all}) {Text(if(all) "收起" else "展开这段")}
        }
    }
    val phone=points.filter {it.text("origin")=="phone"}
    if(phone.isNotEmpty()) TextButton(onClick={expanded=!expanded}) {Text(if(expanded) "收起手机补充" else "手机补充 ${report.optInt("phone_marker_count",phone.size)} 处")}
    if(expanded) phone.take(40).forEach {Text("手机添加 · ${markerTime(it.optLong("offset_ms"))}",style=MaterialTheme.typography.bodyMedium)}
}

internal fun markerTime(ms:Long): String {
    return "${clock(ms)}.${(ms%1000).toString().padStart(3,'0')}"
}
