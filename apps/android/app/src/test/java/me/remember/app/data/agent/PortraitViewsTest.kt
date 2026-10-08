package me.remember.app.data.agent

import org.junit.Assert.*
import org.junit.Test

class PortraitViewsTest {
    private fun observation(id: String, dimension: String, time: String? = null, attrs: Map<String, String> = emptyMap(), status: String = "ACTIVE") =
        MemoryObservation(id, dimension, "合成观察", "合成原句", "ev_$id", 0, 4, time, "2026-10-08T10:00:00Z", "REPORTED", attrs, "synthetic", "SUBJECT", status)
    private fun portrait(observations: List<MemoryObservation>) = AgentPortrait("subject", 2,
        observations.map { PortraitSource(it.evidenceId, it.quote, "SUBJECT", "ep_${it.id}") }, emptyList(), observations = observations)
    @Test fun recalledMoodWithoutEventTimeDoesNotUseTheRecordingDate() {
        val graph = portrait(listOf(observation("old", "mood", attrs = mapOf("time_scope" to "EVENT", "valence" to "NEGATIVE")),
            observation("now", "mood", attrs = mapOf("time_scope" to "TELLING", "valence" to "POSITIVE"))))
        val points = graph.views().moods
        assertNull(points.first().date); assertEquals("2026-10-08", points.last().date)
    }
    @Test fun eventTimelineKeepsPlansAndUnknownDatesDistinctWithoutInventingCausality() {
        val graph = portrait(listOf(observation("unknown", "event", attrs = mapOf("kind" to "HAPPENED")),
            observation("plan", "event", "2026-11-01", mapOf("kind" to "PLANNED")),
            observation("actual", "event", "2026-10-01", mapOf("kind" to "HAPPENED"))))
        assertEquals(listOf("actual", "plan", "unknown"), graph.views().events.map { it.id })
        assertEquals("PLANNED", graph.views().events[1].attributes["kind"])
    }
    @Test fun preferencesAreNotDecisionsAndCorrectedObservationsDoNotStayInTheChart() {
        val graph = portrait(listOf(observation("preference", "identity", attrs = mapOf("facet" to "PREFERENCE", "value" to "乒乓球")),
            observation("old", "event", attrs = mapOf("choice" to "薪水"), status = "SUPERSEDED"),
            observation("decision", "event", attrs = mapOf("options" to "薪水/成长", "choice" to "成长", "reason" to "学习机会"))))
        assertEquals(1, graph.views().decisions.size); assertEquals("成长", graph.views().decisions.single().choice)
        assertFalse(graph.views().events.any { it.id == "old" })
    }
    @Test fun duplicateTranscriptsAreNotIndependentExpressionSamples() {
        val graph = portrait(listOf(observation("one", "expression", attrs = mapOf("feature" to "慢慢来")),
            observation("two", "expression", attrs = mapOf("feature" to "慢慢来"))))
        assertEquals(1, graph.views().expressions.single().independentSamples)
    }
}
