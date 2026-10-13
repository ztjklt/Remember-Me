package me.remember.app.hardware

import org.junit.Assert.*
import org.junit.Test

class Work3200SessionTest {
    private val scope = HardwareScope("https://example.invalid", "actor-a", "subject-a")
    private fun authorized() = HardwareAuthResult(true, true, false, 0, false, null)

    @Test fun offlineRejectionCanBeFollowedByOnlineSuccess() {
        val session = Work3200Session { 1000L }
        val ticket = session.begin(scope)
        session.onAuth(ticket, HardwareAuthResult(false, false, false, 0, false, HardwareAuthError(1002)))
        assertFalse(session.state.canUseDevice)
        assertEquals(HardwareAuthPhase.AWAITING_ONLINE, session.state.authPhase)
        session.onAuth(ticket, authorized())
        assertTrue(session.state.canUseDevice)
    }

    @Test fun expiredTokenEvenWithSdkSuccessRequiresRenewal() {
        val session = Work3200Session { 1000L }
        val ticket = session.begin(scope)
        session.onAuth(ticket, HardwareAuthResult(true, true, false, 0, true, HardwareAuthError(8003)))
        assertEquals(HardwareAuthPhase.RENEWAL_REQUIRED, session.state.authPhase)
        assertFalse(session.state.canUseDevice)
        assertFalse(session.connected(ticket, "device-a"))
    }

    @Test fun expiredOfflineLicenseCannotAuthorizeDeviceCommands() {
        val session = Work3200Session { 1000L }
        val ticket = session.begin(scope)
        session.onAuth(ticket, HardwareAuthResult(true, false, true, 1000, false, null))
        assertFalse(session.state.canUseDevice)
        session.onAuth(ticket, HardwareAuthResult(true, false, true, 1001, false, null))
        assertTrue(session.state.canUseDevice)
    }

    @Test fun formerAccountCallbacksCannotRepopulateCurrentSession() {
        val session = Work3200Session { 1000L }
        val old = session.begin(scope)
        session.onAuth(old, authorized())
        assertTrue(session.connected(old, "device-a"))
        val current = session.begin(scope.copy(actorId = "actor-b"))
        assertFalse(session.onAuth(old, authorized()))
        assertFalse(session.connected(old, "device-a"))
        assertNull(session.state.deviceKey)
        session.onAuth(current, authorized())
        assertTrue(session.connected(current, "device-b"))
        session.close()
        assertFalse(session.onAuth(current, authorized()))
    }

    @Test fun fileListingAndTransferRejectStaleOperationsAndWrongDevice() {
        val session = Work3200Session { 1000L }
        val ticket = session.begin(scope)
        session.onAuth(ticket, authorized()); session.connected(ticket, "device-a")
        val listing = session.beginListing(ticket)
        val first = DeviceRecording(1700000000, 0, 160, 20, 0)
        assertTrue(session.onFiles(listing, "device-a", listOf(first), false))
        assertFalse(session.state.listComplete)
        assertFalse(session.onFiles(listing, "other", listOf(first), true))
        session.onFiles(listing, "device-a", listOf(first), true)
        assertEquals(1, session.state.files.size)
        assertTrue(session.state.listComplete)
        assertFalse(session.onFiles(listing, "device-a", emptyList(), true))
        val transfer = session.beginTransfer(ticket, first.fileId)
        assertTrue(session.onTransfer(transfer, "device-a", HardwareTransferPhase.TRANSFERRING, 80, 160))
        assertEquals(80L, session.state.transfer?.receivedBytes)
        assertFalse(session.onTransfer(transfer, "device-a", HardwareTransferPhase.TRANSFERRING, 20, 160))
        session.disconnected(ticket, "device-a")
        assertEquals(HardwareTransferPhase.INTERRUPTED, session.state.transfer?.phase)
        assertFalse(session.onTransfer(transfer, "device-a", HardwareTransferPhase.FILE_RECEIVED, 160, 160))
    }

    @Test fun sdkTransferCompleteIsNotAnUploadableAudioClaim() {
        val session = Work3200Session { 1000L }
        val ticket = session.begin(scope)
        session.onAuth(ticket, authorized()); session.connected(ticket, "device-a")
        val listing = session.beginListing(ticket)
        session.onFiles(listing, "device-a", listOf(DeviceRecording(1, 0, 160, 20, 0)), true)
        val transfer = session.beginTransfer(ticket, 1)
        session.onTransfer(transfer, "device-a", HardwareTransferPhase.FILE_RECEIVED, 160, 160)
        assertEquals(HardwareTransferPhase.FILE_RECEIVED, session.state.transfer?.phase)
        assertFalse(Work3200Capabilities().canStartRecording)
        assertFalse(Work3200Capabilities().canStopRecording)
    }

    @Test fun credentialStringRepresentationNeverIncludesCredentialOrIdentityValues() {
        val credentials = Work3200Credentials("private-user", "private-phone", "unit-token", "unit-license", "unit-signature", HardwareEnvironment.DEVELOPMENT)
        val printed = credentials.toString()
        listOf("private-user", "private-phone", "unit-token", "unit-license", "unit-signature").forEach { assertFalse(printed.contains(it)) }
    }

    @Test fun duplicateConnectionDoesNotEraseAnInFlightTransfer() {
        val session = Work3200Session { 1000L }
        val ticket = session.begin(scope)
        session.onAuth(ticket, authorized()); session.connected(ticket, "device-a")
        val listing = session.beginListing(ticket)
        session.onFiles(listing, "device-a", listOf(DeviceRecording(1, 0, 160, 20, 0)), true)
        val transfer = session.beginTransfer(ticket, 1)
        session.onTransfer(transfer, "device-a", HardwareTransferPhase.TRANSFERRING, 80, 160)
        session.connected(ticket, "device-a")
        assertEquals(80L, session.state.transfer?.receivedBytes)
        assertTrue(session.onTransfer(transfer, "device-a", HardwareTransferPhase.FILE_RECEIVED, 160, 160))
    }

    @Test fun lateTransferStatusCannotReturnSdkProcessingToTransferring() {
        val session = Work3200Session { 1000L }
        val ticket = session.begin(scope)
        session.onAuth(ticket, authorized()); session.connected(ticket, "device-a")
        session.onFiles(session.beginListing(ticket), "device-a", listOf(DeviceRecording(1, 0, 160, 20, 0)), true)
        val transfer = session.beginTransfer(ticket, 1)
        session.onTransfer(transfer, "device-a", HardwareTransferPhase.SDK_PROCESSING, 160, 160)
        assertFalse(session.onTransfer(transfer, "device-a", HardwareTransferPhase.TRANSFERRING, 160, 160))
        assertEquals(HardwareTransferPhase.SDK_PROCESSING, session.state.transfer?.phase)
    }
}
