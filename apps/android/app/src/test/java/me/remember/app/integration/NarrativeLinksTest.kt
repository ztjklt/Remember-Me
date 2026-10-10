package me.remember.app.integration

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class NarrativeLinksTest {
    private fun record(id:String, kind:String, source:String, status:String="confirmed", valid:Boolean=true) = JSONObject()
        .put("id",id).put("kind",kind).put("status",status).put("source_valid",valid).put("evidence_ids",JSONArray().put(source))

    @Test fun onlyVisibleConfirmedStoriesWithSharedEvidenceAreLinked() {
        val person=record("person","person","source-a")
        val rows=listOf(record("shared","story","source-a"),record("unrelated","story","source-b"),
            record("pending","story","source-a","pending"),record("stale","story","source-a",valid=false),
            record("another-person","person","source-a"))
        assertEquals(listOf("shared"),relatedNarrativeStories(person,rows).map{it.getString("id")})
        person.put("status","pending")
        assertTrue(relatedNarrativeStories(person,rows).isEmpty())
    }

    @Test fun disappearingSourceDoesNotRetainOldStoryLink() {
        val person=record("person","person","source-a")
        val story=record("shared","story","source-a")
        assertEquals(1,relatedNarrativeStories(person,listOf(story)).size)
        assertTrue(relatedNarrativeStories(person,emptyList()).isEmpty())
        story.put("source_valid",false)
        assertTrue(relatedNarrativeStories(person,listOf(story)).isEmpty())
    }
}
