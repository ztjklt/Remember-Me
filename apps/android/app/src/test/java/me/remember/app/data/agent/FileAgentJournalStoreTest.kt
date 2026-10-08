package me.remember.app.data.agent

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class FileAgentJournalStoreTest {
    @get:Rule val files = TemporaryFolder()
    @Test fun failedReplacementAndUnknownVersionPreservePublishedPayload() {
        val path = File(files.newFolder(), "journal.json"); val store = FileAgentJournalStore(path)
        val original = JSONObject().put("version", 99).put("subject_id", "one")
        store.write(original); assertEquals(original.toString(), store.read()!!.toString())
        try { AgentMemoryEngine("one", store, TestAgentModel()); fail("version reset") } catch (_: IllegalStateException) {}
        File(path.parentFile, "journal.json.pending").mkdir()
        assertTrue(runCatching { store.write(JSONObject().put("new", true)) }.isFailure)
        assertEquals(original.toString(), path.readText())
    }
    @Test fun corruptPayloadIsRetainedAndNotSilentlyReplacedByAnEmptyJournal() {
        val path = files.newFile().apply { writeText("unreadable-original") }
        try { FileAgentJournalStore(path).read(); fail("corrupt journal ignored") } catch (_: IllegalStateException) {}
        assertEquals("unreadable-original", path.readText())
    }
}
