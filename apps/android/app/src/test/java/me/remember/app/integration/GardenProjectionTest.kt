package me.remember.app.integration

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class GardenProjectionTest {
    private fun evidence(id: String, episode: String) = JSONObject().put("evidence_id", id)
        .put("episode_id", episode).put("excerpt", "我当时明确说过的话").put("source_type", "SUBJECT")
    private fun memory(id: String, evidenceId: String, episode: String) = JSONObject()
        .put("memory_item_id", id).put("content", "一条真实记忆 $id").put("review_state", "active")
        .put("memory_type", "EVENT").put("source_type", "SUBJECT")
        .put("evidence", JSONArray().put(evidence(evidenceId, episode)))
    private fun episode(id: String, vararg memories: JSONObject) = JSONObject().put("episode_id", id)
        .put("status", "ready").put("reviewed", true).put("recorded_at", "2026-10-10T12:00:00Z")
        .put("memories", JSONArray(memories.toList()))
    private fun record(id: String, vararg refs: JSONObject) = JSONObject().put("id", id)
        .put("kind", "story").put("status", "confirmed").put("source_valid", true)
        .put("title", "本人核对的故事 $id").put("text", "有来源的故事内容")
        .put("facets", JSONArray().put("EXPERIENCE"))
        .put("evidence", JSONArray(refs.toList()))
    private fun narrative(vararg records: JSONObject) = JSONObject().put("records", JSONArray(records.toList()))
        .put("source_evidence", JSONArray(listOf("e1" to "ep", "e2" to "ep", "ea" to "a", "eb" to "b", "eg" to "good", "quote" to "ep")
            .map { evidence(it.first, it.second) }))

    @Test fun overlappingInvalidSourceCannotReviveAnActiveSiblingSummary() {
        val recording = episode("ep", memory("sibling", "e1", "ep"))
        val data = narrative(record("old", evidence("e1", "ep")).put("source_valid", false))
            .put("source_evidence", JSONArray())
        assertTrue(projectGarden(listOf(recording), data).isEmpty())
    }
    @Test fun partiallyInvalidBasisCannotKeepTheEntireSummary() {
        val m = memory("partial", "e1", "ep")
        m.getJSONArray("evidence").put(evidence("stale", "ep"))
        assertTrue(projectGarden(listOf(episode("ep", m)), narrative()).isEmpty())
    }
    @Test fun completedEmptyExtractionKeepsARecordingEntryWithoutInventingPetals() {
        val cluster = projectGarden(listOf(episode("ep")), narrative()).single()
        assertFalse(cluster.organized)
        assertTrue(cluster.petals.isEmpty())
        assertEquals(listOf("ep"), cluster.episodeIds)
    }
    @Test fun aStoryCannotDisplayTheWholeSummaryFromOnlyPartOfItsValidBasis() {
        val m = memory("partial", "e1", "ep")
        m.getJSONArray("evidence").put(evidence("e2", "ep"))
        val cluster = projectGarden(listOf(episode("ep", m)), narrative(record("r", evidence("e1", "ep"))))
            .first{it.id=="record:r"}
        assertFalse(cluster.petals.any{it.id=="partial"})
        assertEquals("evidence:e1",cluster.petals.single().id)
    }

    @Test fun sharedRecordingDoesNotMergeUnrelatedMemories() {
        val recording = episode("ep", memory("m1", "e1", "ep"), memory("m2", "e2", "ep"))
        val clusters = projectGarden(listOf(recording), narrative(record("r1", evidence("e1", "ep")), record("r2", evidence("e2", "ep"))))
        assertEquals(listOf("m1"), clusters.first { it.id == "record:r1" }.petals.map { it.id })
        assertEquals(listOf("m2"), clusters.first { it.id == "record:r2" }.petals.map { it.id })
        assertFalse(clusters.any { !it.organized })
    }
    @Test fun reviewFailureAndUnavailableSourcesDoNotBloom() {
        val good = episode("good", memory("mg", "eg", "good"))
        val waiting = episode("waiting", memory("mw", "ew", "waiting")).put("waiting_for_review", true)
        val failed = episode("failed", memory("mf", "ef", "failed")).put("status", "failed")
        val revoked = episode("revoked", memory("mr", "er", "revoked")).put("unavailable", true)
        val unreviewed = episode("unchecked", memory("mu", "eu", "unchecked")).put("reviewed", false)
        assertEquals(listOf("episode:good"), projectGarden(listOf(good, waiting, failed, revoked, unreviewed), narrative()).map { it.id })
    }
    @Test fun confirmedStoryCanConnectTwoRecordingsButDraftCannot() {
        val stories = listOf(episode("a", memory("ma", "ea", "a")), episode("b", memory("mb", "eb", "b")))
        val story = record("joined", evidence("ea", "a"), evidence("eb", "b"))
        val cluster = projectGarden(stories, narrative(story)).single()
        assertTrue(cluster.organized)
        assertEquals(listOf("a", "b"), cluster.episodeIds)
        assertEquals(setOf("ma", "mb"), cluster.petals.map { it.id }.toSet())
        story.put("status", "pending")
        assertEquals(2, projectGarden(stories, narrative(story)).size)
    }
    @Test fun revokedPartOfCrossRecordingStoryCannotLeakItsTitle() {
        val story = record("private-title", evidence("ea", "a"), evidence("eb", "b"))
        val clusters = projectGarden(listOf(episode("a", memory("ma", "ea", "a"))), narrative(story))
        assertFalse(clusters.any { it.id == "record:private-title" })
        assertEquals("episode:a", clusters.single().id)
    }
    @Test fun unmatchedMemoryRemainsAvailableAndDuplicatesDoNotMultiply() {
        val first = memory("m1", "e1", "ep")
        val recording = episode("ep", first, first, memory("m2", "e2", "ep"))
        val clusters = projectGarden(listOf(recording), narrative(record("r", evidence("e1", "ep"))))
        assertEquals(listOf("m2"), clusters.single { !it.organized }.petals.map { it.id })
        assertEquals(2, clusters.sumOf { it.petals.size })
    }
    @Test fun invalidNarrativeIsHiddenAndDeletedMemoryIsExcluded() {
        val recording = episode("ep", memory("m1", "e1", "ep").put("review_state", "superseded"), memory("m2", "e2", "ep"))
        val invalid = record("stale", evidence("e1", "ep")).put("source_valid", false)
        assertEquals(listOf("m2"), projectGarden(listOf(recording), narrative(invalid)).single().petals.map { it.id })
    }
    @Test fun storyWithoutMatchingMemoryShowsEvidenceRatherThanInventedMemory() {
        val recording = episode("ep")
        val cluster = projectGarden(listOf(recording), narrative(record("r", evidence("quote", "ep")))).single()
        assertEquals("evidence:quote", cluster.petals.single().id)
        assertEquals("故事依据 · 核对文字", cluster.petals.single().sourceLabel)
    }
    @Test fun noMaterialsProduceAnEmptyGarden() {
        assertTrue(projectGarden(emptyList(), narrative()).isEmpty())
    }
}
