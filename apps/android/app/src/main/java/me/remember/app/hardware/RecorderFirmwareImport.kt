package me.remember.app.hardware

import org.json.JSONObject
import java.io.File
import java.io.InputStream
import java.security.MessageDigest
import java.util.UUID
import java.util.zip.ZipFile

/** User-selected official binaries plus explicit model/version/checksums. Never fetches firmware. */
object RecorderFirmwareImport {
    fun read(input: InputStream, root: File): RecorderFirmware {
        val directory = File(root, UUID.randomUUID().toString()).apply { check(mkdirs()) }
        val archive = File(directory, "firmware.zip")
        input.use { source -> archive.outputStream().use { out ->
            val buffer = ByteArray(65536); var total = 0
            while(true) { val n = source.read(buffer); if(n < 0) break; total += n; require(total <= 20 * 1024 * 1024); out.write(buffer,0,n) }
        } }
        return ZipFile(archive).use { zip ->
            val manifestEntry = zip.getEntry("manifest.json") ?: error("Missing manifest")
            val bytes = zip.getInputStream(manifestEntry).use { source ->
                val out=java.io.ByteArrayOutputStream(); val buffer=ByteArray(4096)
                while(true) { val n=source.read(buffer); if(n<0) break; require(out.size()+n<=16384); out.write(buffer,0,n) }; out.toByteArray()
            }
            val manifest = JSONObject(bytes.toString(Charsets.UTF_8))
            require(manifest.getString("product") == "D3200" && manifest.getString("sdk") == "1.3.02")
            fun part(name: String): Pair<String, File>? {
                val entry = manifest.optJSONObject(name) ?: return null
                val version = entry.getString("version"); require(version.matches(Regex("[0-9]{2}\\.[0-9]{2}")))
                val fileName = entry.getString("file"); require(fileName.matches(Regex("[A-Za-z0-9_.-]+\\.bin")))
                val expected = entry.getString("sha256").lowercase(); require(expected.matches(Regex("[0-9a-f]{64}")))
                val item = zip.getEntry(fileName) ?: error("Missing binary")
                val file = File(directory,"$name.bin")
                val digest = MessageDigest.getInstance("SHA-256")
                zip.getInputStream(item).use { source -> file.outputStream().use { out ->
                    val buffer=ByteArray(65536); var total=0
                    while(true) { val n=source.read(buffer); if(n<0) break; total+=n; require(total<=8*1024*1024); digest.update(buffer,0,n); out.write(buffer,0,n) }
                    require(total>0)
                } }
                require(digest.digest().joinToString("") { "%02x".format(it) } == expected)
                return version to file
            }
            val bt=part("bt"); val wifi=part("wifi"); require(bt!=null || wifi!=null)
            RecorderFirmware(bt?.first,wifi?.first,bt?.second,wifi?.second)
        }
    }
}
