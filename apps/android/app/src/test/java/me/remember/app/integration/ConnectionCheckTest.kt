package me.remember.app.integration

import java.net.SocketTimeoutException
import javax.net.ssl.SSLHandshakeException
import org.junit.Assert.*
import org.junit.Test

class ConnectionCheckTest {
    @Test fun knownApiWithClosedRegistrationOffersAdminLogin() {
        val result = connectedService(ServiceInfo(apiVersion = "0.7.0"))
        assertEquals(ConnectionPhase.READY, result.phase)
        assertTrue(result.message.contains("内测账号"))
    }
    @Test fun unknownOrMissingVersionIsNotClaimedCompatible() {
        assertEquals(ConnectionPhase.INCOMPATIBLE, connectedService(ServiceInfo(apiVersion = "0.8.0")).phase)
        assertEquals(ConnectionPhase.INCOMPATIBLE, connectedService(ServiceInfo()).phase)
    }
    @Test fun wrappedTlsFailureDoesNotSuggestDisablingVerification() {
        val result = failedConnection(IllegalStateException("wrapper", SSLHandshakeException("details")))
        assertTrue(result.message.contains("不要关闭"))
        assertFalse(result.message.contains("details"))
    }
    @Test fun timeoutShowsNetworkAndServiceHelpInsteadOfKeyRequest() {
        val result = failedConnection(SocketTimeoutException())
        assertEquals(ConnectionPhase.FAILED, result.phase)
        assertTrue(result.message.contains("服务器和网络"))
        assertFalse(result.message.contains("密钥"))
    }
}
