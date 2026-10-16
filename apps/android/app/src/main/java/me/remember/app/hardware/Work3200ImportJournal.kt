package me.remember.app.hardware

import org.json.JSONObject
import java.io.File
import java.nio.channels.FileChannel
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption
import java.security.MessageDigest
import java.util.UUID

data class HardwareImport(val importId: String, val idempotencyKey: String, val episodeId: String?)
data class HardwareDownloadReceipt(val importId: String, val fileId: Int, val bytes: Long, val sha256: String, val rawFile: File,
    val deviceKey: String = "", val durationMs: Long = 0)
data class HardwareUploadCandidate(val file: File, val audio: PreparedHardwareAudio, val idempotencyKey: String, val episodeId: String?, val source: String = "WORK_3200")

/** Pass a dedicated app-private root; vendor downloads and prepared derivatives have separate folders. */
class Work3200ImportJournal(directory: File) {
    companion object { private val locks = java.util.concurrent.ConcurrentHashMap<String, Any>() }
    private val root = directory.apply { require(mkdirs() || isDirectory) }.canonicalFile
    val rawDirectory: File = File(root, "raw").apply { require(mkdirs() || isDirectory) }
    val preparedDirectory: File = File(root, "prepared").apply { require(mkdirs() || isDirectory) }
    private val entries = File(root, "entries").apply { require(mkdirs() || isDirectory) }
    private val annotations = File(root, "markers").apply { require(mkdirs() || isDirectory) }
    private fun identityId(scope: HardwareScope, deviceKey: String, fileId: Int): String {
        requireDeviceKey(deviceKey); require(fileId > 0)
        val bytes = listOf(scope.server, scope.actorId, scope.subjectId, deviceKey, fileId.toString())
            .joinToString("") { "${it.toByteArray(Charsets.UTF_8).size}:$it" }.toByteArray(Charsets.UTF_8)
        return MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    }
    private fun readMarkers(id: String): List<RecorderMark> {
        val file = File(annotations, "$id.json")
        if (!file.exists()) return emptyList()
        val values = org.json.JSONArray(file.readText())
        return (0 until values.length()).map { values.getJSONObject(it).let { item -> RecorderMark(item.getLong("ms"), item.getString("origin")) } }
    }
    fun markers(scope: HardwareScope, deviceKey: String, fileId: Int): List<RecorderMark> = locked { readMarkers(identityId(scope, deviceKey, fileId)) }
    fun markers(id: String, scope: HardwareScope): List<RecorderMark> = locked { requireScope(load(id), scope); readMarkers(id) }
    private fun packetFile(id: String) = File(annotations,"$id.device-packets.json")
    private fun packetMarks(id: String): JSONObject = packetFile(id).takeIf {it.exists()}?.let {JSONObject(it.readText())} ?: JSONObject()
    fun recordDeviceSignal(scope: HardwareScope, deviceKey: String, fileId: Int, fingerprint: String? = null) = locked {
        val id=identityId(scope,deviceKey,fileId)
        val row=packetMarks(id)
        val old=row.optJSONArray("hashes") ?: org.json.JSONArray()
        val hashes=(0 until old.length()).map {old.getString(it)}.toMutableSet()
        if(fingerprint!=null && fingerprint.matches(Regex("[0-9a-f]{64}")) && hashes.size<500) hashes.add(fingerprint)
        row.put("signal",true).put("hashes",org.json.JSONArray(hashes.toList()))
        val pending=File(annotations,"${UUID.randomUUID()}.pending")
        try {pending.outputStream().use {it.write(row.toString().toByteArray());it.fd.sync()}
            Files.move(pending.toPath(),packetFile(id).toPath(),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE)
        } finally {pending.delete()}
    }
    fun resolveDevicePackets(id: String, scope: HardwareScope, durationMs: Long): List<RecorderMark> = locked {
        requireScope(load(id),scope)
        val row=packetMarks(id);val hashes=row.optJSONArray("hashes") ?: org.json.JSONArray()
        DeviceMarkerPackets.locate(receipt(load(id),scope).rawFile,(0 until hashes.length()).map {hashes.getString(it)}.toSet(),durationMs)
            .map {RecorderMark(it,"device")}
    }
    fun deviceMarkerPending(id: String, scope: HardwareScope): Boolean = locked {
        requireScope(load(id),scope)
        packetMarks(id).optBoolean("signal") && readMarkers(id).none {it.origin=="device"}
    }
    fun saveMarkers(scope: HardwareScope, deviceKey: String, fileId: Int, marks: List<RecorderMark>) = locked {
        val id = identityId(scope, deviceKey, fileId)
        val merged = (readMarkers(id) + marks).distinct().sortedBy { it.offsetMs }
        val pending = File(annotations, "${UUID.randomUUID()}.pending")
        try {
            val json = org.json.JSONArray().apply { merged.forEach { put(JSONObject().put("ms", it.offsetMs).put("origin", it.origin)) } }
            pending.outputStream().use { it.write(json.toString().toByteArray()); it.fd.sync() }
            Files.move(pending.toPath(), File(annotations, "$id.json").toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
        } finally { pending.delete() }
    }

    private fun within(file: File, parent: File): File = file.canonicalFile.also {
        require(it.toPath().startsWith(parent.canonicalFile.toPath()) && it != parent.canonicalFile && it.isFile && it.length() > 0) { "File must remain inside its private import directory" }
        require(parent.canonicalFile.toPath().startsWith(root.toPath())) { "Import directory escaped its private root" }
    }
    private fun sha(file: File): String = file.inputStream().use { stream ->
        val digest = MessageDigest.getInstance("SHA-256"); val buffer = ByteArray(65536)
        while (true) { val count = stream.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
        digest.digest().joinToString("") { "%02x".format(it) }
    }
    private fun entryFile(id: String): File {
        require(id.matches(Regex("[0-9a-f]{64}"))) { "Invalid import identifier" }
        require(entries.canonicalFile.toPath().startsWith(root.toPath()))
        return File(entries, "$id.json")
    }
    private fun view(row: JSONObject) = HardwareImport(row.getString("id"), row.getString("key"), row.optString("episode").takeIf { it.isNotBlank() })
    private fun load(id: String): JSONObject = JSONObject(within(entryFile(id), entries).readText()).also { require(it.getString("id") == id) }
    private fun receipt(row: JSONObject, scope: HardwareScope): HardwareDownloadReceipt {
        requireScope(row, scope)
        val file = within(File(root, row.getString("raw")), rawDirectory)
        val digest = sha(file)
        require(digest == row.getString("raw_sha256")) { "本机录音校验未通过，请重新下载。" }
        return HardwareDownloadReceipt(row.getString("id"), row.getJSONObject("identity").getInt("file"), file.length(), digest, file,
            row.getJSONObject("identity").getString("device"), row.getLong("duration_ms"))
    }
    fun rawReceipt(id: String, scope: HardwareScope): HardwareDownloadReceipt = locked { receipt(load(id), scope) }
    fun downloaded(scope: HardwareScope): List<HardwareDownloadReceipt> = locked {
        entries.listFiles().orEmpty().filter { it.extension == "json" }.mapNotNull {
            runCatching { receipt(load(it.nameWithoutExtension), scope) }.getOrNull()
        }.sortedByDescending { it.fileId }
    }
    private fun requireScope(row: JSONObject, scope: HardwareScope) {
        val identity = row.getJSONObject("identity")
        require(identity.getString("server") == scope.server && identity.getString("actor") == scope.actorId && identity.getString("subject") == scope.subjectId) { "Import belongs to another account or subject" }
    }
    private fun save(row: JSONObject) {
        val target = entryFile(row.getString("id"))
        val pending = File(entries, "${UUID.randomUUID()}.pending")
        try {
            pending.outputStream().use { it.write(row.toString().toByteArray()); it.fd.sync() }
            Files.move(pending.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
        } finally { pending.delete() }
    }
    private fun <T> locked(block: () -> T): T = synchronized(locks.computeIfAbsent(root.path) { Any() }) { FileChannel.open(File(root, "journal.lock").toPath(), StandardOpenOption.CREATE, StandardOpenOption.WRITE).use {
        channel -> channel.lock().use { block() }
    } }
    fun recordDownloaded(scope: HardwareScope, deviceKey: String, file: DeviceRecording, raw: File): HardwareImport = locked {
        requireDeviceKey(deviceKey)
        val original = within(raw, rawDirectory); val digest = sha(original)
        val identity = JSONObject().put("server", scope.server).put("actor", scope.actorId).put("subject", scope.subjectId)
            .put("device", deviceKey).put("file", file.fileId)
        // Length-prefix components avoid delimiter collisions across account and device identities.
        val id = identityId(scope, deviceKey, file.fileId)
        val target = entryFile(id)
        if (target.exists()) {
            val row = load(id)
            require(row.getString("raw_sha256") == digest) { "Device file identifier conflicts with existing bytes" }
            require(sha(within(File(root, row.getString("raw")), rawDirectory)) == digest) { "Retained original changed" }
            view(row)
        } else {
            val row = JSONObject().put("id", id).put("key", "work3200-${UUID.randomUUID()}").put("identity", identity)
                .put("raw", root.toPath().relativize(original.toPath()).toString()).put("raw_sha256", digest)
                .put("end_time", file.endTime).put("size", file.sizeBytes).put("duration_ms", file.durationMs).put("code", file.code)
            save(row); view(row)
        }
    }
    fun prepare(id: String, scope: HardwareScope, audio: File, decoderVersion: String): HardwareImport = locked {
        require(decoderVersion.isNotBlank())
        val row = load(id); requireScope(row, scope)
        val output = within(audio, preparedDirectory)
        Work3200Audio.inspectPcmWav(output)
        val digest = sha(output)
        if (row.has("episode")) {
            require(row.getString("prepared_sha256") == digest) { "An uploaded import cannot be replaced" }
            candidate(row)
            return@locked view(row)
        }
        require(!row.has("prepared_sha256") || row.getString("prepared_sha256") == digest) { "Prepared audio is immutable for this upload key" }
        row.put("prepared", root.toPath().relativize(output.toPath()).toString()).put("prepared_sha256", digest).put("decoder_version", decoderVersion)
        save(row); view(row)
    }
    fun uploadCandidate(id: String, scope: HardwareScope): HardwareUploadCandidate = locked {
        val row = load(id); requireScope(row, scope); candidate(row)
    }
    private fun candidate(row: JSONObject): HardwareUploadCandidate {
        require(row.has("prepared")) { "Raw SDK audio requires a verified decoder before upload" }
        require(sha(within(File(root, row.getString("raw")), rawDirectory)) == row.getString("raw_sha256")) { "Retained original changed" }
        val file = within(File(root, row.getString("prepared")), preparedDirectory)
        require(sha(file) == row.getString("prepared_sha256")) { "Prepared audio changed" }
        val entry = view(row)
        return HardwareUploadCandidate(file, Work3200Audio.inspectPcmWav(file), entry.idempotencyKey, entry.episodeId)
    }
    fun markUploaded(id: String, scope: HardwareScope, episodeId: String): HardwareImport = locked {
        require(episodeId.isNotBlank()); val row = load(id); requireScope(row, scope); candidate(row)
        require(!row.has("episode") || row.getString("episode") == episodeId) { "Import already belongs to a different Episode" }
        row.put("episode", episodeId); save(row); view(row)
    }
}
