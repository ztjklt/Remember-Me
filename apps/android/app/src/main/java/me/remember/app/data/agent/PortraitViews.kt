package me.remember.app.data.agent

data class MoodPoint(val observation: MemoryObservation, val date: String?, val scope: String, val valence: String)
data class DecisionStep(val observation: MemoryObservation, val options: String, val choice: String, val reason: String, val value: String)
data class ExpressionSample(val feature: String, val examples: List<MemoryObservation>, val independentSamples: Int)
data class FourPortraitViews(val events: List<MemoryObservation>, val moods: List<MoodPoint>, val decisions: List<DecisionStep>,
    val values: List<PortraitLink>, val expressions: List<ExpressionSample>)

/** Numerical values and graph membership come from validated records, never free-form graph generation. */
fun AgentPortrait.views(): FourPortraitViews {
    val active = observations.filter { it.status == "ACTIVE" }
    val moods = active.filter { it.dimension == "mood" }.map { o ->
        val scope = o.attributes.getValue("time_scope")
        // A remembered mood with unknown event time must not become today's mood.
        MoodPoint(o, o.eventTime ?: o.recordedAt.take(10).takeIf { scope == "TELLING" && it.length == 10 }, scope, o.attributes.getValue("valence"))
    }
    val decisions = active.filter { it.dimension == "event" && !it.attributes["choice"].isNullOrBlank() }.map { o ->
        DecisionStep(o, o.attributes["options"].orEmpty(), o.attributes.getValue("choice"), o.attributes["reason"].orEmpty(), o.attributes["value"].orEmpty())
    }
    val expressions = active.filter { it.dimension == "expression" }.groupBy { it.attributes["feature"] ?: it.summary }.map { (feature, examples) ->
        val originals = examples.mapNotNull { o -> sources.firstOrNull { it.id == o.evidenceId && it.sourceType == "SUBJECT" } }
        val distinct = originals.distinctBy { it.episodeId }.map { it.excerpt.replace(Regex("\\s+"), "") }.distinct().size
        ExpressionSample(feature, examples, distinct)
    }
    return FourPortraitViews(active.filter { it.dimension == "event" }.sortedBy { it.eventTime ?: "9999" }, moods,
        decisions, links.filter { it.domain in setOf("VALUES", "DECISION_PATTERNS") }, expressions)
}
