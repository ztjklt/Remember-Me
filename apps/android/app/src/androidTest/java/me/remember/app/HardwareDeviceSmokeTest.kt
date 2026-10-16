package me.remember.app

import android.os.ParcelFileDescriptor
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.hardware.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Explicit opt-in via instrumentation class; no physical Bluetooth result is implied. */
class HardwareDeviceSmokeTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext

    @Test fun decodeKnownSyntheticOpusIntoPcm() {
        val source = File(context.cacheDir, "synthetic-device.raw")
        instrumentation.context.assets.open("synthetic-device.raw").use { input -> source.outputStream().use { input.copyTo(it) } }
        val out = File(context.cacheDir, "synthetic-${System.nanoTime()}.wav")
        val decoded = DeviceOpusDecoder.decode(source, out)
        val format = Work3200Audio.inspectPcmWav(decoded)
        assertEquals(2, format.channels)
        assertEquals(source.length() / 160 * 20, format.durationMs)
        assertTrue(format.byteSize > source.length())
        val bytes = decoded.readBytes()
        val samples = java.nio.ByteBuffer.wrap(bytes, 44, bytes.size - 44).order(java.nio.ByteOrder.LITTLE_ENDIAN).asShortBuffer()
        var energy = 0.0; var count = 0
        while (samples.hasRemaining()) { val sample = samples.get().toDouble(); energy += sample * sample; count++ }
        assertTrue("decoded tone must contain signal", kotlin.math.sqrt(energy / count) > 100)
    }

    @Test fun vendorGrantAuthenticatesInsidePackagedSdk() {
        val json = ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand("cat /data/local/tmp/remember-hardware-smoke.json"))
            .bufferedReader().use { JSONObject(it.readText()) }
        val scope = HardwareScope("https://39.108.183.47", json.getString("user_id"), "synthetic-smoke")
        val credentials = HardwareGrant.parse(json, scope, json.getString("device_id"))
        val done = CountDownLatch(1)
        var success = false
        val transport = HardwareTransportFactory.create(object : HardwareEvents {
            override fun auth(result: HardwareAuthResult) { if (result.isOnline) { success = result.success && !result.tokenExpired; done.countDown() } }
            override fun found(productCode: String?, name: String?, mac: String?, uuid: String?) { }
            override fun connected() { }
            override fun disconnected(systemCode: Int?) { }
            override fun info(battery: Int?, firmware: String?, freeKb: Int?, totalKb: Int?) { }
            override fun binding(confirmed: Boolean) { }
            override fun files(files: List<DeviceRecording>, complete: Boolean) { }
            override fun transfer(fileId: Int, sdkStatus: Int) { }
            override fun progress(fileId: Int, receivedBytes: Int, totalBytes: Int, sequenceNumber: Int, marked: Boolean) { }
            override fun receivedSdkFile(fileId: Int, rawFile: File) { }
            override fun markers(fileId: Int, offsetsMs: IntArray) { }
            override fun error(operation: String, code: Int) { }
        })
        try {
            instrumentation.runOnMainSync { transport.initialize(context.applicationContext, credentials) }
            assertTrue("online vendor callback must arrive", done.await(60, TimeUnit.SECONDS))
            assertTrue("vendor authorization must succeed", success)
        } finally { instrumentation.runOnMainSync { transport.close() } }
    }
}
