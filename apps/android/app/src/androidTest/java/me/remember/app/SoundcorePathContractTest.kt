package me.remember.app

import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.hardware.SoundcoreSavePath
import me.remember.app.hardware.DeviceOpusDecoder
import me.remember.app.hardware.Work3200Audio
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.util.UUID

/** Executes the PRIVATE supplied AAR path builder, not a reimplementation or a fake SDK. */
class SoundcorePathContractTest {
    @Test fun vendorOutputRemainsInsideRequestedDirectory() {
        assumeTrue(BuildConfig.SOUNDCORE_ENABLED)
        val root = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "sdk-path-${UUID.randomUUID()}").apply { mkdirs() }.canonicalFile
        val type = Class.forName("com.oceanwing.soundcore.spplink.device.D3200Device")
        val device = type.getConstructor(String::class.java, String::class.java, String::class.java)
            .newInstance("D3200", "00:00:00:00:00:00", "path-test")
        val field = type.getDeclaredField("mSaveFolder").apply { isAccessible = true }
        field.set(device, SoundcoreSavePath.directoryArgument(root))
        val path = type.getMethod("getFilePath", Integer::class.java).invoke(device, 1700000000) as String
        assertEquals("The real SDK must create a child, not a sibling", root, File(path).canonicalFile.parentFile)
        assertEquals("1700000000.opus", File(path).name)
        // Use the vendor's actual packet writer with synthetic Opus; verify the
        // resulting file can be found, byte-checked and decoded by production code.
        val bytes = InstrumentationRegistry.getInstrumentation().context.assets.open("synthetic-device.raw").use { it.readBytes() }
        // Supply the real Android persistence implementation without opening a
        // Bluetooth/auth session. In production initSDK supplies this Context.
        val storageType = Class.forName("com.oceanwing.soundcore.spplink.storage.PersistentStorageUtil")
        val storageField = storageType.getDeclaredField("impl").apply { isAccessible = true }
        val previousStorage = storageField.get(null)
        val storage = Class.forName("com.oceanwing.soundcore.spplink.storage.PersistentStorageImpl")
            .getConstructor(Any::class.java).newInstance(InstrumentationRegistry.getInstrumentation().targetContext)
        storageField.set(null, storage)
        val writerType = Class.forName("com.oceanwing.soundcore.spplink.service.audio.FileWriterManager")
        val companion = writerType.getField("Companion").get(null)
        val writer = companion.javaClass.getMethod("getINSTANCE").invoke(companion)
        val threadType = Class.forName("com.oceanwing.soundcore.spplink.service.bluetooth.BluetoothThreadManager")
        val threads = threadType.getConstructor().newInstance()
        threadType.getMethod("init").invoke(threads)
        writerType.getMethod("init", threadType).invoke(writer, threads)
        try {
        val platform = Class.forName("com.oceanwing.soundcore.spplink.Platform_androidKt")
        val write = platform.getMethod("writeToFile", Int::class.javaPrimitiveType, String::class.java, ByteArray::class.java)
        bytes.asList().chunked(160).forEachIndexed { sequence, packet -> write.invoke(null, sequence, path, packet.toByteArray()) }
        val completed = java.util.concurrent.CountDownLatch(1)
        var flushed = false
        val completion: (Boolean) -> Unit = { ok -> flushed = ok; completed.countDown() }
        platform.getMethod("notifyFileTransferComplete", String::class.java, kotlin.jvm.functions.Function1::class.java)
            .invoke(null, path, completion)
        assertTrue("SDK writer completion", completed.await(15, java.util.concurrent.TimeUnit.SECONDS))
        assertTrue("SDK writer flushed all packets", flushed)
        assertArrayEquals(bytes, File(path).readBytes())
        val wav = DeviceOpusDecoder.decode(File(path), File(root, "playable.wav"))
        assertTrue(Work3200Audio.inspectPcmWav(wav).durationMs > 0)
        } finally {
        writerType.getMethod("close").invoke(writer)
        threadType.getMethod("forceShutdown").invoke(threads)
        storageField.set(null, previousStorage)
        }
    }
}
