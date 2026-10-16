package me.remember.app

import android.graphics.Bitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.hardware.*
import me.remember.app.integration.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.net.ServerSocket
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

/** Real production UI/network/ledger/decoder; loopback backend + SDK events are
 * explicitly simulated. No real account or microphone is used. */
class AutomaticCaptureFlowTest {
    @get:Rule val ui=createAndroidComposeRule<MainActivity>()
    private val inst get()=InstrumentationRegistry.getInstrumentation()
    @Test fun automaticUploadRetryDraftPersistenceAndOneSave() {
        CaptureServer().use { server ->
            val model=ViewModelProvider(ui.activity)[NativeWorkbenchModel::class.java]
            fun await(test: () -> Boolean) = ui.waitUntil(90000,test)
            fun main(block: () -> Unit)=ui.runOnIdle(block)
            fun login(token: String="owner-a") {
                await { !model.ui.value.busy }
                main { model.connect(server.url,token) }
                await { model.ui.value.owner && !model.ui.value.busy }
                assertNull(model.ui.value.error)
            }
            login()
            val journal=Work3200ImportJournal(File(ui.activity.filesDir,"work3200-imports"))
            val identity=model.hardwareScope()
            val raw=File(journal.rawDirectory,"auto-${System.nanoTime()}.raw")
            raw.writeBytes(inst.context.assets.open("synthetic-device.raw").use { it.readBytes() })
            val id=(System.currentTimeMillis()/1000).toInt()
            val imported=journal.recordDownloaded(identity,"simulated-auto",DeviceRecording(id,0,raw.length().toInt(),2000,0),raw)
            val wav=DeviceOpusDecoder.decode(raw,File(journal.preparedDirectory,"${imported.importId}.wav"))
            journal.prepare(imported.importId,identity,wav,"android-mediacodec-fixed160-v1")
            val receipt=journal.rawReceipt(imported.importId,identity)
            val candidate=journal.uploadCandidate(imported.importId,identity)
            main { model.acceptRecorderAudio(receipt,candidate); model.acceptRecorderAudio(receipt,candidate) }
            await { model.ui.value.captureErrors.isNotEmpty() }
            assertFalse("network retry must not lock the whole app",model.ui.value.busy)
            assertEquals(1,model.ui.value.local.count { it.key==candidate.idempotencyKey })
            await { model.ui.value.drafts.isNotEmpty() && model.ui.value.local.any { it.key==candidate.idempotencyKey && it.linked } }
            assertEquals(2,server.uploadRequests.get())
            assertEquals(1,server.episodes.size)
            val ep=model.ui.value.local.single { it.key==candidate.idempotencyKey }.episode
            assertTrue(model.ui.value.drafts[ep]!!.text.contains("图书馆"))
            assertEquals(0,server.saves.get()) // autosave != confirming or AI extraction
            ui.onNodeWithTag("capture-draft-text").performScrollTo().performTextReplacement("今天去图书馆借了一本书。")
            main { model.editDraft(ep,model.ui.value.drafts.getValue(ep).text,"和老朋友一起去的。") }
            // The store writes on IO. Waiting for the lock gives a deterministic
            // persistence check instead of an arbitrary sleep before restart.
            val key=java.security.MessageDigest.getInstance("SHA-256").digest("${server.url}|owner-a|subject-a".toByteArray()).joinToString("") { "%02x".format(it) }
            val file=File(ui.activity.filesDir,"capture-drafts/$key.json")
            await { runCatching { file.readText().contains("老朋友") }.getOrDefault(false) }
            main { model.logout() }; login("owner-b")
            assertTrue(model.ui.value.local.isEmpty()); assertTrue(model.ui.value.drafts.isEmpty())
            main { model.logout() }; login()
            assertEquals("今天去图书馆借了一本书。",model.ui.value.drafts.getValue(ep).text)
            assertEquals("和老朋友一起去的。",model.ui.value.drafts.getValue(ep).supplement)
            assertEquals(2,server.uploadRequests.get()) // restart must not re-upload linked audio
            ui.onNodeWithTag("capture-draft-text").performScrollTo()
            shot("01-draft-simulated-backend")
            ui.onNodeWithTag("capture-save-memory").performScrollTo().performClick()
            await { !model.ui.value.busy && model.ui.value.drafts.isEmpty() }
            assertNull(model.ui.value.error)
            assertEquals(1,server.saves.get())
            assertTrue(server.savedBody!!.has("cloud_analysis_consent_id"))
            assertEquals("今天去图书馆借了一本书。",server.savedBody!!.getString("transcript"))
            assertEquals("和老朋友一起去的。",server.savedBody!!.getString("supplement"))
            ui.waitUntil(10000) {ui.onAllNodesWithText("已加入记忆").fetchSemanticsNodes().isNotEmpty()}
            ui.onNodeWithText("已加入记忆").assertIsDisplayed()
            shot("02-memory-simulated-backend")
            val calls=server.spaceRequests.get()
            Thread.sleep(10000)
            assertEquals("idle polling must not repeat full workbench refresh",calls,server.spaceRequests.get())
            server.readerOnly=true
            main { model.onForeground(true) }
            await { !model.ui.value.owner }
            assertTrue(model.ui.value.local.isEmpty()); assertTrue(model.ui.value.drafts.isEmpty())
            assertNull(model.ui.value.reviewEpisode)
            main { model.logout() }
        }
    }
    private fun shot(name: String) {
        ui.waitForIdle()
        val dir=File(ui.activity.getExternalFilesDir(null),"automatic-capture-proof").apply { mkdirs() }
        val bitmap=inst.uiAutomation.takeScreenshot()
        File(dir,"$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) }; bitmap.recycle()
        File(dir,"evidence.json").writeText(JSONObject().put("physical_device",false).put("backend","loopback test double")
            .put("ui","production Compose").put("decoder","real Android MediaCodec").toString(2))
    }
}

private class CaptureServer: AutoCloseable {
    private val socket=ServerSocket(0,10,java.net.InetAddress.getByName("127.0.0.1"))
    private val executor=Executors.newSingleThreadExecutor()
    val url get()="http://127.0.0.1:${socket.localPort}"
    val episodes=java.util.concurrent.ConcurrentHashMap<String,JSONObject>()
    val uploadRequests=AtomicInteger(); val saves=AtomicInteger(); val spaceRequests=AtomicInteger()
    @Volatile var savedBody: JSONObject?=null
    @Volatile var readerOnly=false
    init { executor.submit {
        while(!socket.isClosed) runCatching { socket.accept().use { connection ->
            connection.soTimeout=15000
            val input=connection.getInputStream().buffered()
            fun line(): String { val b=StringBuilder(); while(true) { val c=input.read(); if(c<0 || c==10) break; if(c!=13)b.append(c.toChar()) }; return b.toString() }
            val request=line().split(' '); val headers=mutableMapOf<String,String>()
            while(true) { val l=line(); if(l.isEmpty())break; headers[l.substringBefore(':').lowercase()]=l.substringAfter(':').trim() }
            val body=java.io.ByteArrayOutputStream()
            if(headers["transfer-encoding"]=="chunked") while(true) {
                val size=line().substringBefore(';').toInt(16); if(size==0) {line();break}
                repeat(size) {body.write(input.read())};line()
            } else repeat(headers["content-length"]?.toInt() ?: 0) {body.write(input.read())}
            val (code,response)=respond(request[0],request[1],headers,body.toString("UTF-8"))
            val bytes=response.toByteArray()
            connection.getOutputStream().write("HTTP/1.1 $code Test\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n\r\n".toByteArray()+bytes)
        } }
    } }
    private fun respond(method: String,path: String,headers: Map<String,String>,body: String): Pair<Int,String> {
        val b=headers["authorization"]?.endsWith("owner-b")==true
        if(path=="/api/v1/workbench/spaces") { spaceRequests.incrementAndGet(); return 200 to JSONObject().put("actor_id",if(b)"owner-b" else "owner-a")
            .put("display_name","流程测试").put("items",JSONArray().put(JSONObject().put("subject_id",if(b)"subject-b" else "subject-a").put("display_name","模拟人物").put("role","owner"))).toString() }
        if(path=="/api/v1/workbench/capabilities") return 200 to "{\"stt\":\"paraformer\",\"stt_processing\":\"cloud\",\"stt_configured\":true,\"cloud_asr_policy\":\"test-policy\"}"
        if(path.startsWith("/api/v1/consents?")) return 200 to "[{\"scope\":\"RECORDING\",\"status\":\"granted\",\"consent_id\":\"recording\"},{\"scope\":\"CLOUD_TWIN\",\"status\":\"granted\",\"consent_id\":\"analysis\"}]"
        if(path=="/api/v1/episodes" && method=="POST") {
            val number=uploadRequests.incrementAndGet()
            // Emulate server commit followed by a lost success response.
            episodes.putIfAbsent("ep-auto",JSONObject().put("episode_id","ep-auto").put("status","transcribing").put("waiting_for_review",true)
                .put("recorded_at","2026-10-16T10:00:00Z").put("transcript","今天去图书馆。"))
            return if(number==1) 503 to "{\"error_message\":\"temporary test failure\"}" else 201 to "{\"episode_id\":\"ep-auto\"}"
        }
        if(path.endsWith("/stories")) return 200 to JSONObject().put("role",if(readerOnly)"reader" else "owner").put("items",JSONArray(if(b || readerOnly)emptyList<JSONObject>() else episodes.values.toList())).toString()
        if(path.endsWith("/transcript-review")) {
            if(method=="PATCH") {
                savedBody=JSONObject(body); saves.incrementAndGet()
                episodes.getValue("ep-auto").put("waiting_for_review",false).put("reviewed",true).put("status","ready")
                    .put("memories",JSONArray().put(JSONObject().put("content","今天和老朋友去图书馆借书。")))
                    .put("cumulative_analysis",JSONObject().put("status","complete"))
                return 200 to "{\"status\":\"ready\"}"
            }
            return 200 to "{\"state\":\"reviewing\",\"transcript\":\"今天去图书馆。\",\"machine_transcript\":\"今天去图书馆。\"}"
        }
        return 200 to "{}"
    }
    override fun close() { socket.close(); executor.shutdownNow() }
}
