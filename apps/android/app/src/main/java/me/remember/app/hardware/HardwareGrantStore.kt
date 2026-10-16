package me.remember.app.hardware

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class HardwareGrantStore(context: Context, scope: HardwareScope) {
    private val root = File(context.noBackupFilesDir, "work3200-grants").apply { mkdirs() }
    private val alias = "remember-hardware-grants-v1"
    private val name = MessageDigest.getInstance("SHA-256").digest("${scope.server}\u0000${scope.actorId}".toByteArray())
        .joinToString("") { "%02x".format(it) }
    private val grant = AtomicFile(File(root, "$name.enc"))
    val deviceId: String = File(root, "installation-id").let {
        if (it.exists()) it.readText() else "rm-install-${UUID.randomUUID()}".also { id -> it.writeText(id) }
    }
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    fun save(value: JSONObject) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val bytes = cipher.iv + cipher.doFinal(value.toString().toByteArray(Charsets.UTF_8))
        val output = grant.startWrite()
        try { output.write(bytes); grant.finishWrite(output) } catch (e: Exception) { grant.failWrite(output); throw e }
    }
    fun load(): JSONObject? = runCatching {
        val bytes = grant.readFully()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
        }
        JSONObject(cipher.doFinal(bytes.copyOfRange(12, bytes.size)).toString(Charsets.UTF_8))
    }.getOrNull()
}
