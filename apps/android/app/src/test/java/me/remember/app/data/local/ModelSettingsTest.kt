package me.remember.app.data.local

import org.junit.Assert.*
import org.junit.Test

class ModelSettingsTest {
    @Test fun endpointsRejectCredentialLeaksAndInsecureRemoteTransport() {
        for (url in listOf("http://api.example/v1", "https://key@api.example/v1", "https://api.example?key=x", "https://api.example#x")) {
            assertThrows(IllegalArgumentException::class.java) { ModelEndpoint(url, "test", "secret").validate() }
        }
        ModelEndpoint("https://api.example/v1", "test", "secret").validate()
    }
    @Test fun credentialsRoundTripButNeverAppearInDebugStrings() {
        val endpoint = ModelEndpoint("https://api.example/v1", "test", "private-test-key")
        val settings = LocalModelSettings(endpoint, endpoint, SpeechProtocol.DASHSCOPE)
        assertEquals(settings, LocalModelSettings.from(settings.json()))
        assertFalse(endpoint.toString().contains(endpoint.apiKey))
        assertFalse(settings.toString().contains(endpoint.apiKey))
    }
}
