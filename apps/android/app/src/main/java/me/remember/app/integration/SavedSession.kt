package me.remember.app.integration

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Only a device session is saved. Provider keys and passwords never enter this store. */
class SavedSession(context: Context) {
    private val preferences = context.getSharedPreferences("remember-session", Context.MODE_PRIVATE)
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey("remember-session-v1", null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder("remember-session-v1", KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    fun save(server: String, token: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val data = cipher.doFinal(JSONObject().put("server", server).put("token", token).toString().toByteArray(Charsets.UTF_8))
        check(preferences.edit().putString("data", Base64.encodeToString(data, Base64.NO_WRAP))
            .putString("iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP)).commit()) { "无法保存登录状态。" }
    }
    fun load(): Pair<String, String>? = runCatching {
        val data = preferences.getString("data", null) ?: return null
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(preferences.getString("iv", ""), Base64.NO_WRAP))) }
        val parsed = JSONObject(cipher.doFinal(Base64.decode(data, Base64.NO_WRAP)).toString(Charsets.UTF_8))
        parsed.getString("server") to parsed.getString("token")
    }.getOrElse { clear(); null }
    fun clear() { preferences.edit().clear().commit() }
}

/** Authentication has no pre-existing SessionGate snapshot. Redirects are refused. */
fun accountRequest(server: String, action: String, body: JSONObject = JSONObject(), token: String? = null): JSONObject {
    require(action in listOf("login", "register", "logout"))
    val connection = java.net.URI(normalizeServer(server) + "/api/v1/accounts/" + action).toURL().openConnection() as java.net.HttpURLConnection
    try {
        connection.requestMethod = "POST"; connection.connectTimeout = 15_000; connection.readTimeout = 30_000
        connection.instanceFollowRedirects = false; connection.useCaches = false; connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        if(token != null) connection.setRequestProperty("Authorization", "Bearer $token")
        connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        val status = connection.responseCode
        val text = (if(status in 200..299) connection.inputStream else connection.errorStream)?.bufferedReader()?.use { it.readText() }.orEmpty()
        val result = runCatching { JSONObject(text) }.getOrDefault(JSONObject())
        check(status in 200..299) { result.optString("error_message").ifBlank { "连接未完成（$status），请检查服务地址。" } }
        return result
    } finally { connection.disconnect() }
}
