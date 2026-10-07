package me.remember.app.data.local

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** One transaction publishes the local journal, model revision and answer together. */
interface LocalStateStore {
    fun read(): JSONObject?
    fun write(state: JSONObject)
}

class SqliteLocalState(context: Context, name: String = "local-agent.db") : SQLiteOpenHelper(context, name, null, 1), LocalStateStore {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE journal (id INTEGER PRIMARY KEY CHECK(id = 1), payload TEXT NOT NULL)")
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = error("Unsupported local database version")
    override fun read(): JSONObject? = readableDatabase.rawQuery("SELECT payload FROM journal WHERE id=1", null).use {
        if (it.moveToFirst()) JSONObject(it.getString(0)) else null
    }
    override fun write(state: JSONObject) {
        writableDatabase.insertWithOnConflict("journal", null, ContentValues().apply {
            put("id", 1); put("payload", state.toString())
        }, SQLiteDatabase.CONFLICT_REPLACE).also { check(it != -1L) { "本地保存失败。" } }
    }
}

/** The whole configuration is encrypted; neither endpoint keys nor drafts enter preferences. */
class LocalSettingsStore(context: Context) {
    private val file = AtomicFile(File(context.noBackupFilesDir, "local-models.enc"))
    private val alias = "remember-me-local-models-v1"
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        return store.getKey(alias, null) as? SecretKey ?: KeyGenerator.getInstance("AES", "AndroidKeyStore").run {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
            generateKey()
        }
    }
    fun read(): JSONObject? {
        if (!file.baseFile.exists() && !File(file.baseFile.path + ".bak").exists()) return null
        val bytes = file.openRead().use { it.readBytes() }
        require(bytes.size > 28) { "模型配置损坏，请重新配置。" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
        return JSONObject(String(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8))
    }
    fun write(settings: JSONObject) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val bytes = cipher.iv + cipher.doFinal(settings.toString().toByteArray(Charsets.UTF_8))
        val output = file.startWrite()
        try { output.write(bytes); file.finishWrite(output) }
        catch (e: Exception) { file.failWrite(output); throw e }
    }
    fun clear() { file.delete() }
}
