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
    fun preserve(state: JSONObject) {}
}

class LocalRecoveryRequired(message: String) : IllegalStateException(message)

class SqliteLocalState(context: Context, name: String = "local-agent.db", version: Int = 1) : SQLiteOpenHelper(context, name, null, version), LocalStateStore {
    private val recovery = File(context.noBackupFilesDir, "$name.payload.bak")
    private fun preserveRaw(payload: String) {
        val atomic = AtomicFile(recovery)
        val output = atomic.startWrite()
        try { output.write(payload.toByteArray(Charsets.UTF_8)); atomic.finishWrite(output) }
        catch (e: Exception) { atomic.failWrite(output); throw e }
    }
    override fun preserve(state: JSONObject) = preserveDatabase(readableDatabase)
    fun clearRecovery() { AtomicFile(recovery).delete() }
    fun recoveryText(): String {
        val raw = AtomicFile(recovery).openRead().bufferedReader().use { it.readText() }
        return JSONObject(raw).optJSONArray("materials")?.objects().orEmpty().joinToString("\n\n") {
            "${it.optString("source_ref")}\n${it.optString("excerpt")}"
        }.ifBlank { "没有可导出的原文。原始日志仍在本机，请使用兼容版本恢复。" }
    }
    private fun preserveDatabase(db: SQLiteDatabase) {
        db.rawQuery("SELECT payload FROM journal WHERE id=1", null).use { if (it.moveToFirst()) preserveRaw(it.getString(0)) }
    }
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE journal (id INTEGER PRIMARY KEY CHECK(id = 1), payload TEXT NOT NULL)")
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        preserveDatabase(db)
        if (oldVersion != 1 || newVersion != 2) throw LocalRecoveryRequired("数据库版本不兼容，已保存原始日志。请导出原文并升级应用。")
        // Version 2 retains the journal table; future structural migrations must be explicit.
    }
    override fun onDowngrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        preserveDatabase(db)
        throw LocalRecoveryRequired("请使用更新版本打开资料。原始日志已保留，可导出原文。")
    }
    override fun read(): JSONObject? = readableDatabase.rawQuery("SELECT payload FROM journal WHERE id=1", null).use {
        if (!it.moveToFirst()) null else {
            val raw = it.getString(0)
            try { JSONObject(raw) } catch (_: Exception) {
                preserveRaw(raw)
                throw LocalRecoveryRequired("本地日志无法解析，原始内容已保留，请勿清除应用数据。")
            }
        }
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
