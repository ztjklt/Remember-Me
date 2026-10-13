package me.remember.app.integration

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SimpleExperienceTest {
    private fun story(id: String, status: String = "ready", reviewed: Boolean = true,
        waiting: Boolean = false, unavailable: Boolean = false) = JSONObject()
        .put("episode_id", id).put("status", status).put("reviewed", reviewed)
        .put("waiting_for_review", waiting).put("unavailable", unavailable)

    @Test fun listeningNeverPublishesUnavailableOrUnreviewedStories() {
        val rows = listOf(story("good"), story("good"), story("revoked", unavailable=true),
            story("draft", reviewed=false), story("pending", waiting=true), story("failed", status="failed"), story(""))
        assertEquals(listOf("good"), simpleListeningStories(rows).map { it.text("episode_id") })
        assertEquals(7, rows.size)
    }
    @Test fun changingVisibilityRemovesTheListeningEntry() {
        assertEquals(1, simpleListeningStories(listOf(story("shared"))).size)
        assertTrue(simpleListeningStories(listOf(story("shared", unavailable=true))).isEmpty())
        assertTrue(simpleListeningStories(emptyList()).isEmpty())
    }
    @Test fun onlyOwnersHavePendingWorkAndReadyStoriesAreNotCounted() {
        val rows = listOf(story("good"), story("failed", status="failed"), story("review", waiting=true),
            story("review", waiting=true), story("gone", status="failed", unavailable=true))
        val owner = NativeState(space=JSONObject().put("role", "owner"), stories=rows)
        assertEquals(2, simplePendingCount(owner))
        assertEquals(0, simplePendingCount(owner.copy(space=JSONObject().put("role", "reader"))))
    }
}
