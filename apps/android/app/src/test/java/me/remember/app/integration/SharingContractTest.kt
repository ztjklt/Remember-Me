package me.remember.app.integration

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SharingContractTest {
    @Test fun grantCloudPermissionUnderstandsLegacyIntegerWithoutTruthiness() {
        assertTrue(cloudProcessingAllowed(JSONObject().put("cloud_processing_allowed",1)))
        assertTrue(cloudProcessingAllowed(JSONObject().put("cloud_processing_allowed",true)))
        for(value in listOf<Any>(0,false,2,-1,"1","yes",JSONObject.NULL)) {
            assertFalse(cloudProcessingAllowed(JSONObject().put("cloud_processing_allowed",value)))
        }
        assertFalse(cloudProcessingAllowed(JSONObject()))
    }
    @Test fun legacyServerWithoutCapabilityEndpointKeepsCoreLoginAndClosedFeatures() {
        val info = loadServiceInfo { throw BackendHttpException(404, "Not Found") }
        assertFalse(info.registrationAllowed)
        assertFalse(info.invitations)
        assertEquals("", info.release)
    }
    @Test fun capabilityFallbackDoesNotMaskAuthorizationNetworkOrServerErrors() {
        for(status in listOf(401,403,429,500)) {
            val error=assertThrows(BackendHttpException::class.java) {
                loadServiceInfo { throw BackendHttpException(status,"rejected") }
            }
            assertEquals(status,error.status)
        }
        assertThrows(java.io.IOException::class.java) { loadServiceInfo { throw java.io.IOException("offline") } }
        assertTrue(loadServiceInfo { JSONObject().put("sharing_invitations",true) }.invitations)
    }
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
