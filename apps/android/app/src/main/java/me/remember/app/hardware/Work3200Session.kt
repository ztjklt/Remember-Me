package me.remember.app.hardware

import java.util.UUID

class HardwareSessionTicket internal constructor(val id: String)
class HardwareOperationTicket internal constructor(val session: HardwareSessionTicket, val id: String, val deviceKey: String)

/** Pure event state. A future SDK binding captures tickets when registering callbacks, never at delivery. */
class Work3200Session(private val nowSeconds: () -> Long = { System.currentTimeMillis() / 1000 }) {
    private var current: HardwareSessionTicket? = null
    private var listing: HardwareOperationTicket? = null
    private var transfer: HardwareOperationTicket? = null
    @Volatile var state = HardwareSessionState()
        private set

    @Synchronized fun begin(scope: HardwareScope): HardwareSessionTicket {
        close()
        state = HardwareSessionState(scope, HardwareAuthPhase.AUTHENTICATING)
        return HardwareSessionTicket(UUID.randomUUID().toString()).also { current = it }
    }
    @Synchronized fun close() {
        current = null; listing = null; transfer = null; state = HardwareSessionState()
    }
    @Synchronized fun onAuth(ticket: HardwareSessionTicket, result: HardwareAuthResult): Boolean {
        if (ticket != current) return false
        val phase = when {
            result.tokenExpired -> HardwareAuthPhase.RENEWAL_REQUIRED
            result.success && (result.isOnline || result.licenseValid && result.licenseExpireTime > nowSeconds()) -> HardwareAuthPhase.AUTHORIZED
            !result.isOnline -> HardwareAuthPhase.AWAITING_ONLINE
            else -> HardwareAuthPhase.REJECTED
        }
        state = state.copy(auth = result, authPhase = phase)
        if (!state.canUseDevice) invalidateConnection()
        return true
    }
    private fun valid(ticket: HardwareSessionTicket): Boolean {
        if (ticket != current || !state.canUseDevice) return false
        val auth = state.auth ?: return false
        if (!auth.isOnline && auth.licenseExpireTime <= nowSeconds()) {
            state = state.copy(authPhase = HardwareAuthPhase.RENEWAL_REQUIRED)
            invalidateConnection(); return false
        }
        return true
    }
    @Synchronized fun connected(ticket: HardwareSessionTicket, deviceKey: String): Boolean {
        requireDeviceKey(deviceKey)
        if (!valid(ticket)) return false
        if (state.deviceKey == deviceKey) return true
        invalidateConnection()
        state = state.copy(deviceKey = deviceKey, files = emptyList(), listComplete = false, transfer = null)
        return true
    }
    @Synchronized fun disconnected(ticket: HardwareSessionTicket, deviceKey: String): Boolean {
        if (ticket != current || state.deviceKey != deviceKey) return false
        invalidateConnection(); return true
    }
    private fun invalidateConnection() {
        listing = null; transfer = null
        state = state.copy(deviceKey = null, files = emptyList(), listComplete = false,
            transfer = state.transfer?.takeUnless { it.phase == HardwareTransferPhase.FILE_RECEIVED }?.copy(phase = HardwareTransferPhase.INTERRUPTED))
    }
    @Synchronized fun beginListing(ticket: HardwareSessionTicket): HardwareOperationTicket {
        require(valid(ticket) && state.deviceKey != null && listing == null && transfer == null) { "Device is not ready for a file list" }
        state = state.copy(files = emptyList(), listComplete = false)
        return HardwareOperationTicket(ticket, UUID.randomUUID().toString(), state.deviceKey!!).also { listing = it }
    }
    @Synchronized fun onFiles(ticket: HardwareOperationTicket, deviceKey: String, files: List<DeviceRecording>, complete: Boolean): Boolean {
        if (!valid(ticket.session) || listing != ticket || deviceKey != ticket.deviceKey || state.deviceKey != deviceKey) return false
        val merged = state.files.associateBy { it.fileId }.toMutableMap()
        files.forEach { file ->
            require(merged[file.fileId] == null || merged[file.fileId] == file) { "Conflicting metadata for a device file" }
            merged[file.fileId] = file
        }
        state = state.copy(files = merged.values.toList(), listComplete = complete)
        if (complete) listing = null
        return true
    }
    @Synchronized fun beginTransfer(ticket: HardwareSessionTicket, fileId: Int): HardwareOperationTicket {
        require(valid(ticket) && state.deviceKey != null && state.listComplete && listing == null && transfer == null) { "Device is not ready to transfer" }
        val file = state.files.single { it.fileId == fileId }
        require(file.code == 0 && file.sizeBytes > 0) { "Device file is unavailable for a new transfer" }
        state = state.copy(transfer = HardwareTransfer(fileId, HardwareTransferPhase.WAITING, totalBytes = file.sizeBytes.toLong()))
        return HardwareOperationTicket(ticket, UUID.randomUUID().toString(), state.deviceKey!!).also { transfer = it }
    }
    @Synchronized fun onTransfer(ticket: HardwareOperationTicket, deviceKey: String, phase: HardwareTransferPhase, received: Long, total: Long): Boolean {
        if (!valid(ticket.session) || transfer != ticket || ticket.deviceKey != deviceKey || state.deviceKey != deviceKey) return false
        val previous = state.transfer ?: return false
        if (phase in setOf(HardwareTransferPhase.WAITING, HardwareTransferPhase.TRANSFERRING, HardwareTransferPhase.SDK_PROCESSING) && phase.ordinal < previous.phase.ordinal) return false
        if (received < previous.receivedBytes || total <= 0 || received > total || total != previous.totalBytes) return false
        if (phase == HardwareTransferPhase.FILE_RECEIVED && received != total) return false
        state = state.copy(transfer = previous.copy(phase = phase, receivedBytes = received))
        if (phase in setOf(HardwareTransferPhase.FILE_RECEIVED, HardwareTransferPhase.FAILED, HardwareTransferPhase.INTERRUPTED)) transfer = null
        return true
    }
}
