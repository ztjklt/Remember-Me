package me.remember.app.data.repository

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** Keeps derived agent data local and reproducible from recording sidecars. */
class LocalAgentStateStore(context: Context) : AgentStateStore {
    private val file = File(context.filesDir, "agent_state.json")

    override fun read(): AgentState = runCatching { file.readText().let(::JSONObject).toState() }.getOrDefault(AgentState())

    override fun write(state: AgentState) {
        val temp = File(file.parentFile, "${file.name}.tmp")
        temp.writeText(state.toJson().toString())
        if (!temp.renameTo(file)) {
            file.writeText(state.toJson().toString())
            temp.delete()
        }
    }

    override fun rebuild(recordings: List<AudioRecording>): AgentState {
        val memories = recordings.flatMap { it.memories }.filter { it.status == "active" }
        val conflicts = ConflictDetector.detect(memories)
        val graph = GraphUpdater.update(AgentState(), memories)
        val model = PersonaSynthesizer.synthesize(PersonModel(), memories)
        return AgentState(model, graph.first, graph.second, conflicts)
    }

    private fun AgentState.toJson() = JSONObject().apply {
        put("personModel", JSONObject().apply {
            put("version", personModel.version)
            put("traits", JSONArray().apply { personModel.traits.forEach { put(JSONObject().apply {
                put("domain", it.domain); put("statement", it.statement); put("confidence", it.confidence)
                put("evidenceMemoryIds", JSONArray(it.evidenceMemoryIds)); put("sourceType", it.sourceType)
            }) } })
        })
        put("nodes", JSONArray().apply { nodes.forEach { put(JSONObject().apply { put("id", it.id); put("label", it.label); put("type", it.type) }) } })
        put("edges", JSONArray().apply { edges.forEach { put(JSONObject().apply { put("from", it.from); put("to", it.to); put("label", it.label); put("evidenceMemoryIds", JSONArray(it.evidenceMemoryIds)) }) } })
        put("conflicts", JSONArray().apply { conflicts.forEach { put(JSONObject().apply { put("memoryId", it.memoryId); put("existingMemoryId", it.existingMemoryId); put("reason", it.reason) }) } })
    }

    private fun JSONObject.toState(): AgentState {
        val p = optJSONObject("personModel")
        val traits = p?.optJSONArray("traits")?.let { a -> buildList { for (i in 0 until a.length()) a.optJSONObject(i)?.let { t -> add(PersonTrait(t.optString("domain"), t.optString("statement"), t.optDouble("confidence", .5).toFloat(), t.optJSONArray("evidenceMemoryIds").strings(), t.optString("sourceType", "SUBJECT"))) } } } ?: emptyList()
        val nodes = optJSONArray("nodes").objects { GraphNode(it.optString("id"), it.optString("label"), it.optString("type")) }
        val edges = optJSONArray("edges").objects { GraphEdge(it.optString("from"), it.optString("to"), it.optString("label"), it.optJSONArray("evidenceMemoryIds").strings()) }
        val conflicts = optJSONArray("conflicts").objects { MemoryConflict(it.optString("memoryId"), it.optString("existingMemoryId"), it.optString("reason")) }
        return AgentState(PersonModel(p?.optString("version", "1") ?: "1", traits), nodes, edges, conflicts)
    }

    private fun JSONArray?.strings(): List<String> = this?.let { a -> buildList { for (i in 0 until a.length()) add(a.optString(i)) } } ?: emptyList()
    private inline fun <T> JSONArray?.objects(map: (JSONObject) -> T): List<T> = this?.let { a -> buildList { for (i in 0 until a.length()) a.optJSONObject(i)?.let { add(map(it)) } } } ?: emptyList()
}

object ConflictDetector {
    fun detect(memories: List<ExtractedMemory>): List<MemoryConflict> {
        val result = mutableListOf<MemoryConflict>()
        memories.forEachIndexed { index, current ->
            memories.take(index).filter { it.kind == current.kind && it.content.isNotBlank() && contradictory(it.content, current.content) }
                .forEach { result += MemoryConflict(current.id, it.id, "同一类别内容出现相反表述") }
        }
        return result
    }

    private fun contradictory(a: String, b: String): Boolean {
        val neg = listOf("不", "没有", "从不", "讨厌", "拒绝", "否认")
        val coreA = a.replace(Regex("不|没有|从不|讨厌|拒绝|否认"), "")
        val coreB = b.replace(Regex("不|没有|从不|讨厌|拒绝|否认"), "")
        return coreA.length >= 3 && coreA == coreB && neg.any(a::contains) != neg.any(b::contains)
    }
}

object GraphUpdater {
    fun update(previous: AgentState, memories: List<ExtractedMemory>): Pair<List<GraphNode>, List<GraphEdge>> {
        val nodes = previous.nodes.toMutableList(); val edges = previous.edges.toMutableList()
        fun node(id: String, label: String, type: String) { if (nodes.none { it.id == id }) nodes += GraphNode(id, label, type) }
        node("subject", "我", "SUBJECT")
        memories.filter { it.kind == "person" || it.kind == "relationship" }.forEach { memory ->
            val label = memory.content.take(32); val id = "person:" + label.hashCode()
            node(id, label, "PERSON")
            if (edges.none { it.from == "subject" && it.to == id && it.label == memory.kind }) edges += GraphEdge("subject", id, memory.kind, listOf(memory.id))
        }
        return nodes to edges
    }
}

object PersonaSynthesizer {
    private val domains = mapOf("person" to "RELATIONSHIPS", "relationship" to "RELATIONSHIPS", "preference" to "PREFERENCES", "value" to "VALUES_BELIEFS", "decision" to "DECISION_PATTERNS", "expression" to "EXPRESSION", "event" to "EPISODIC_MEMORY", "fact" to "IDENTITY", "emotion" to "EPISODIC_MEMORY")
    fun synthesize(previous: PersonModel, memories: List<ExtractedMemory>): PersonModel {
        val traits = previous.traits.toMutableList()
        memories.filter { it.status == "active" }.forEach { m ->
            val domain = domains[m.kind] ?: "EPISODIC_MEMORY"
            traits.removeAll { it.evidenceMemoryIds.contains(m.id) }
            traits += PersonTrait(domain, m.content, m.confidence, listOf(m.id), m.sourceType)
        }
        return PersonModel("1", traits.takeLast(200))
    }
}
