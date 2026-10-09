package me.remember.app.integration

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SharingContractTest {
    @Test fun loginDoesNotOfferRegistrationWithoutExplicitCapability() {
        assertFalse(ServiceInfo.parse(JSONObject()).registrationAllowed)
        assertFalse(ServiceInfo.parse(JSONObject("""{"registration_allowed":false,"sharing_invitations":true}""")).registrationAllowed)
        assertTrue(ServiceInfo.parse(JSONObject("""{"registration_allowed":true}""")).registrationAllowed)
    }
    @Test fun previewBindsSelectionAndVersionAndRequiresWholeAudioConfirmation() {
        val selection=ShareSelection(episodeIds=listOf("ep1"),storyIds=listOf("nr1"))
        val preview=JSONObject().put("source_version","v1")
        assertThrows(IllegalArgumentException::class.java) { selection.invitation(preview,false,true,null) }
        val body=selection.invitation(preview,true,false,null)
        assertEquals("ep1",body.getJSONArray("episode_ids").getString(0))
        assertEquals("nr1",body.getJSONArray("story_ids").getString(0))
        assertEquals("v1",body.getString("source_version"))
        assertFalse(body.getBoolean("cloud_processing_allowed"))
        assertFalse(body.has("recipient_actor_id"))
    }
    @Test fun claimedIsNotAnAuthorizedState() {
        assertEquals("等待本人确认",invitationStatus("claimed"))
        assertEquals("已批准分享",invitationStatus("approved"))
    }
}
