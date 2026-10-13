package me.remember.app.integration
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SpaceFallbackTest {
    @Test fun emptyOrSingleSpaceDoesNotTrapUserInChoiceDialog() {
        val waiting=NativeState(actor="reader",spaceChoiceRequired=true)
        assertFalse(waiting.forSpaceFallback(emptyList(),null).spaceChoiceRequired)
        val only=JSONObject().put("subject_id","only").put("role","reader")
        assertFalse(waiting.forSpaceFallback(listOf(only),initialSpace(listOf(only),null)).spaceChoiceRequired)
        assertEquals("only",waiting.forSpaceFallback(listOf(only),initialSpace(listOf(only),null)).subject)
    }
    @Test fun accessFallbackKeepsOperationGuardAndDropsOldContent() {
        val old=NativeState(actor="reader",actorName="亲友",busy=true,stories=listOf(JSONObject().put("private","old")),
            sharePreview=JSONObject(),player=SourcePlayback(episode="old",playing=true))
        val next=JSONObject().put("subject_id","next")
        val state=old.forSpaceFallback(listOf(next),next)
        assertTrue(state.busy);assertEquals("reader",state.actor);assertEquals("next",state.subject)
        assertTrue(state.stories.isEmpty());assertNull(state.sharePreview);assertFalse(state.player.playing)
    }
}
