package me.remember.app.hardware

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.Rule
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class RecorderFirmwareImportTest {
    @get:Rule val folder=TemporaryFolder()
    private fun archive(product:String="D3200", hash:String?=null, path:String="official.bin"):ByteArray {
        val content="synthetic-test-only-not-firmware".toByteArray()
        val checksum=hash ?: MessageDigest.getInstance("SHA-256").digest(content).joinToString("") { "%02x".format(it) }
        val manifest=JSONObject().put("product",product).put("sdk","1.3.02").put("bt",JSONObject()
            .put("version","04.93").put("file",path).put("sha256",checksum))
        return ByteArrayOutputStream().also { output -> ZipOutputStream(output).use { zip ->
            zip.putNextEntry(ZipEntry("manifest.json"));zip.write(manifest.toString().toByteArray());zip.closeEntry()
            zip.putNextEntry(ZipEntry(path));zip.write(content);zip.closeEntry()
        } }.toByteArray()
    }
    @Test fun importsOnlyMatchingProductAndIntegrity() {
        val result=RecorderFirmwareImport.read(ByteArrayInputStream(archive()),folder.newFolder())
        assertEquals("04.93",result.btVersion);assertTrue(result.btFile!!.isFile);assertNull(result.wifiFile)
    }
    @Test fun refusesWrongProductCorruptBytesAndTraversal() {
        for(bytes in listOf(archive(product="OTHER"),archive(hash="0".repeat(64)),archive(path="../escape.bin"))) {
            try {RecorderFirmwareImport.read(ByteArrayInputStream(bytes),folder.newFolder());fail("Must reject package")}
            catch(expected:IllegalArgumentException) { }
        }
    }
}
