package me.remember.app.data.agent

import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/** Portable Chinese character/word index. No device FTS5 assumption, top-k count or lossy summary. */
class AgentEvidenceIndex(materials: JSONArray, observations: JSONArray = JSONArray()) {
    private val sources = materials.objects().filter { it.getString("source_type") in setOf("SUBJECT", "CALIBRATION") }
    private val observations = observations.objects()
    private val spans = sources.flatMap(::evidenceSpans)
    private val postings = mutableMapOf<String, MutableSet<Int>>()
    init {
        spans.forEachIndexed { index, span ->
            terms(span.getString("excerpt") + " " + span.optString("context")).forEach { postings.getOrPut(it) { mutableSetOf() }.add(index) }
        }
    }
    fun retrieve(question: String, fallback: Boolean = true): JSONArray {
        val expanded = expand(question)
        val selected = terms(expanded).flatMap { postings[it].orEmpty() }.toMutableSet()
        val identity = Regex("我是谁|名字|姓名|叫什么").containsMatchIn(question)
        val relations = Regex("队友|团队|成员|专业|几个人|多少人").containsMatchIn(question)
        observations.filter { o -> o.optString("dimension") == "identity" &&
            (identity && o.getJSONObject("attributes").optString("facet") in setOf("NAME", "EDUCATION", "OCCUPATION") ||
                relations && o.getJSONObject("attributes").optString("facet") == "RELATIONSHIP") }.forEach { observation ->
            spans.forEachIndexed { i, span -> if (parentId(span) == observation.getString("evidence_id") &&
                overlaps(span, observation)) selected.add(i) }
        }
        // Old journals have no observations. Give their small corpus to the model without guessing a taxonomy.
        if (fallback && selected.isEmpty() && sources.sumOf { it.getString("excerpt").length } < 45_000) selected.addAll(spans.indices)
        val roots = selected.map { parentId(spans[it]) }.toMutableSet()
        var changed: Boolean
        do {
            changed = false
            sources.filter { it.getString("source_type") == "CALIBRATION" }.forEach { correction ->
                val related = correction.optJSONArray("related_evidence_ids")?.strings().orEmpty()
                if (correction.getString("evidence_id") in roots || related.any(roots::contains)) {
                    if (roots.add(correction.getString("evidence_id"))) changed = true
                    related.forEach { if (roots.add(it)) changed = true }
                }
            }
        } while (changed)
        // Corrections and their complete dependency set must travel together, including enumeration queries.
        val direct = selected.map { parentId(spans[it]) }.toSet()
        spans.forEachIndexed { i, span ->
            if (parentId(span) in roots && (parentId(span) !in direct || span.getString("source_type") == "CALIBRATION")) selected.add(i)
        }
        val result = JSONArray(selected.sorted().map(spans::get).sortedWith(compareBy<JSONObject> { it.optString("observed_at") }
            .thenBy { if (it.getString("source_type") == "CALIBRATION") 1 else 0 }))
        requireAgentCapacity(JSONObject().put("materials", result))
        return result
    }
    private fun overlaps(span: JSONObject, observation: JSONObject): Boolean = !span.has("span_start") ||
        span.getInt("span_start") < observation.getInt("end") && span.getInt("span_end") > observation.getInt("start")
    private fun expand(question: String): String {
        val groups = listOf(listOf("名字", "姓名", "我是谁", "叫"), listOf("队友", "团队", "成员", "专业", "伙伴"),
            listOf("心情", "情绪", "紧张", "开心", "难过"), listOf("压力", "应对", "散步", "整理想法"),
            listOf("工作", "职业", "毕业", "研究"), listOf("决策", "决定", "选择", "看重", "价值"))
        return question + " " + groups.filter { group -> group.any(question::contains) }.flatten().joinToString(" ")
    }
    private fun terms(text: String): Set<String> {
        val normalized = text.lowercase(Locale.ROOT)
        val words = Regex("[a-z0-9_]+|[\\p{IsHan}]+").findAll(normalized).map { it.value }.toList()
        return words.flatMap { word -> if (word.first().code < 128) listOf(word) else
            word.windowed(2).filterNot { it in setOf("我是", "我的", "什么", "是谁", "一个", "然后", "现在", "时候", "目前") } }.toSet()
    }
}

internal fun parentId(evidence: JSONObject) = evidence.optString("parent_evidence_id", evidence.getString("evidence_id"))
internal fun answerRoots(answer: JSONObject) = answer.getJSONArray("evidence_ids").strings().toSet() +
    answer.optJSONArray("evidence")?.objects().orEmpty().map(::parentId)

internal fun evidenceSpans(source: JSONObject): List<JSONObject> {
    val text = source.getString("excerpt")
    if (text.length <= 6000) return listOf(source.copyJson())
    val result = mutableListOf<JSONObject>(); var offset = 0
    while (offset < text.length) {
        val chunk = sourceChunk(text, offset)
        val start = text.codePointCount(0, offset); val end = start + chunk.codePointCount(0, chunk.length)
        result.add(source.copyJson().put("evidence_id", "span_${source.getString("evidence_id")}_${start}_$end")
            .put("parent_evidence_id", source.getString("evidence_id")).put("excerpt", chunk)
            .put("span_start", start).put("span_end", end).put("source_ref", "${source.getString("source_ref")}#span:$start-$end"))
        offset += chunk.length
    }
    return result
}
