package me.remember.app.hardware

import org.json.JSONObject

/** Checks local identity/expiry; cryptographic verification remains the vendor SDK's job. */
object HardwareGrant {
    fun parse(value: JSONObject, scope: HardwareScope, deviceId: String,
              nowSeconds: Long = System.currentTimeMillis() / 1000): Work3200Credentials {
        require(!value.has("app_key")) { "请选择短期授权文件，不能导入厂商业务密钥。" }
        require(value.getInt("version") == 1) { "授权文件版本不受支持。" }
        require(!value.has("server") || value.getString("server") == scope.server) { "授权文件属于其他服务器。" }
        val user = value.getString("user_id")
        require(user == scope.actorId && value.getString("device_id") == deviceId) { "授权文件与当前账号或手机不匹配。" }
        val license = JSONObject(value.getString("license_json"))
        require(license.getString("user_id") == user && license.getString("device_id") == deviceId) { "授权身份不一致。" }
        require(value.getLong("token_expire_time") > nowSeconds && license.getLong("license_expire_time") > nowSeconds) { "录音豆授权已到期，请重新获取。" }
        val token = value.getString("token")
        val signature = value.getString("license_signature")
        require(token.length in 1..32768 && signature.length in 1..32768) { "授权内容不完整。" }
        return Work3200Credentials(user, deviceId, token, license.toString(), signature,
            HardwareEnvironment.valueOf(value.getString("environment")))
    }
}
