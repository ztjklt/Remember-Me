package me.remember.app.integration

import androidx.compose.material3.*
import androidx.compose.runtime.*
import org.json.JSONObject

@Composable internal fun RecordingHighlights(report: JSONObject?, edited: Boolean = false) {
    if(report==null || report.optInt("marker_count")==0) return
    var expanded by remember(report) { mutableStateOf(false) }
    Text("重点 ${report.optInt("marker_count")} 处 · 已对应文字 ${report.optInt("mapped_count")} 处",style=MaterialTheme.typography.titleSmall)
    if(report.optInt("unmapped_count")>0) Text("有 ${report.optInt("unmapped_count")} 处暂未可靠对应文字；不会猜测位置或自动加权。",style=MaterialTheme.typography.bodySmall)
    if(edited) Text("提交后会按你修改的文字重新核对重点；改写或重复的语句可能无法对应。",style=MaterialTheme.typography.bodySmall)
    if(report.has("prioritized_memory_count")) Text("本次整理有 ${report.optInt("prioritized_memory_count")} 条记忆引用重点片段。",style=MaterialTheme.typography.bodySmall)
    else Text("确认文字后，整理时会优先关注已对应的重点，也会保留其他内容和上下文。",style=MaterialTheme.typography.bodySmall)
    TextButton(onClick={expanded=!expanded}) { Text(if(expanded) "收起重点文字" else "查看重点对应文字") }
    if(expanded) report.rows("spans").forEach { span ->
        Text("${clock(span.optLong("start_ms"))}—${clock(span.optLong("end_ms"))}：${span.text("excerpt")}")
    }
}
