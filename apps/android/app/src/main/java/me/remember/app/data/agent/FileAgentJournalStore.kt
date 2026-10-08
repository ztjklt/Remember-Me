package me.remember.app.data.agent

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption

/** Keep evidence out of Android backup. Each subject has its own journal. */
class AndroidAgentJournalStore(context: Context, subjectId: String) : AgentJournalStore by FileAgentJournalStore(
    File(context.noBackupFilesDir, "agent-memory/${stableDigest(subjectId)}.json")
)

internal class FileAgentJournalStore(private val file: File) : AgentJournalStore {
    override fun read(): JSONObject? {
        if (!file.exists()) return null
        return try { JSONObject(file.readText()) }
        catch (_: Exception) { error("记忆日志无法读取，请保留应用数据并使用兼容版本恢复。") }
    }

    override fun write(state: JSONObject) {
        check(file.parentFile!!.isDirectory || file.parentFile!!.mkdirs()) { "无法创建记忆目录。" }
        val pending = File(file.parentFile, "${file.name}.pending")
        FileOutputStream(pending).use { output ->
            output.write(state.toString().toByteArray(Charsets.UTF_8))
            output.fd.sync()
        }
        // Never fall back to truncating the published journal on a failed replacement.
        Files.move(pending.toPath(), file.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
    }
}
