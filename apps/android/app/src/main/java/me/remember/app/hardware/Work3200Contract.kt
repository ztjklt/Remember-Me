package me.remember.app.hardware

/** These types describe preparation, not a connected or licensed device. */
data class Work3200Capabilities(
    val canStartRecording: Boolean = false,
    val canStopRecording: Boolean = false,
    val canPauseExistingRecording: Boolean = true,
    val canResumeExistingRecording: Boolean = true,
    val canImportOfflineFiles: Boolean = true,
    val canReceiveMarkers: Boolean = true,
    val hasVerifiedAudioDecoder: Boolean = false
)

data class HardwareScope(val server: String, val actorId: String, val subjectId: String) {
    init { require(listOf(server, actorId, subjectId).all { it.isNotBlank() && !it.contains('\u0000') }) }
}
enum class HardwareEnvironment { DEVELOPMENT, PRODUCTION }

/** No app_key belongs on the client. Never use a generated data-class toString here. */
class Work3200Credentials(
    val userId: String, val deviceId: String, val token: String,
    val licenseJson: String, val licenseSignature: String, val environment: HardwareEnvironment
) {
    override fun toString() = "Work3200Credentials([redacted])"
}
fun interface Work3200CredentialProvider {
    suspend fun credentials(scope: HardwareScope): Work3200Credentials?
}
object UnconfiguredWork3200Credentials : Work3200CredentialProvider {
    override suspend fun credentials(scope: HardwareScope): Work3200Credentials? = null
}

/** Preserve the vendor error code; arbitrary vendor text can contain credentials. */
data class HardwareAuthError(val code: Int, val message: String? = null) {
    override fun toString() = "HardwareAuthError(code=$code, message=[redacted])"
}
data class HardwareAuthResult(
    val success: Boolean, val isOnline: Boolean, val licenseValid: Boolean,
    val licenseExpireTime: Long, val tokenExpired: Boolean, val error: HardwareAuthError?
)
enum class HardwareAuthPhase { UNCONFIGURED, AUTHENTICATING, AWAITING_ONLINE, AUTHORIZED, RENEWAL_REQUIRED, REJECTED }

data class DeviceRecording(val fileId: Int, val endTime: Int, val sizeBytes: Int, val durationMs: Int, val code: Int) {
    init { require(fileId > 0 && endTime >= 0 && sizeBytes >= 0 && durationMs >= 0) { "Invalid device file metadata" } }
}
internal fun requireDeviceKey(key: String) {
    require(key.matches(Regex("[A-Za-z0-9_-]{1,128}"))) { "Use a safe local device pseudonym, not a path or MAC address" }
}

enum class HardwareTransferPhase { WAITING, TRANSFERRING, SDK_PROCESSING, FILE_RECEIVED, FAILED, INTERRUPTED }
data class HardwareTransfer(val fileId: Int, val phase: HardwareTransferPhase, val receivedBytes: Long = 0, val totalBytes: Long = 0)
data class HardwareSessionState(
    val scope: HardwareScope? = null, val authPhase: HardwareAuthPhase = HardwareAuthPhase.UNCONFIGURED,
    val auth: HardwareAuthResult? = null, val deviceKey: String? = null,
    val files: List<DeviceRecording> = emptyList(), val listComplete: Boolean = false,
    val transfer: HardwareTransfer? = null
) {
    val canUseDevice get() = authPhase == HardwareAuthPhase.AUTHORIZED
}
