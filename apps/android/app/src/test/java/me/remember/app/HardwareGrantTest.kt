package me.remember.app

import me.remember.app.hardware.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class HardwareGrantTest {
    private val scope = HardwareScope("https://example.com", "actor-a", "subject-a")
    private fun grant() = JSONObject().put("version", 1).put("environment", "DEVELOPMENT")
        .put("user_id", "actor-a").put("device_id", "device-a").put("token", "short-lived")
        .put("token_expire_time", 2000).put("license_signature", "vendor-signature")
        .put("license_json", JSONObject().put("app_id", "test-app").put("user_id", "actor-a")
            .put("device_id", "device-a").put("license_expire_time", 2000).toString())
    @Test fun acceptsMatchingUnexpiredGrant() {
        assertEquals("actor-a", HardwareGrant.parse(grant(), scope, "device-a", 1000).userId)
    }
    @Test fun rejectsAnotherInstallationAndExpiredGrants() {
        for ((device, now) in listOf("other-device" to 1000L, "device-a" to 2000L)) {
            assertThrows(IllegalArgumentException::class.java) { HardwareGrant.parse(grant(), scope, device, now) }
        }
    }
    @Test fun rejectsMismatchingLicenseIdentity() {
        val value = grant().put("license_json", JSONObject(grant().getString("license_json")).put("user_id", "other-user").toString())
        assertThrows(IllegalArgumentException::class.java) { HardwareGrant.parse(value, scope, "device-a", 1000) }
    }
    @Test fun rejectsBusinessCredentialsInImportedFile() {
        assertThrows(IllegalArgumentException::class.java) { HardwareGrant.parse(grant().put("app_key", "never-import"), scope, "device-a", 1000) }
    }
}
