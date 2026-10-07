package me.remember.app

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import me.remember.app.data.local.SqliteLocalState
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LocalStorageInstrumentedTest {
    @Test fun committedJournalSurvivesClosingAndReopeningDatabase() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val name = "local-test-${java.util.UUID.randomUUID()}.db"
        try {
            SqliteLocalState(context, name).use { it.write(JSONObject().put("revision", 2).put("job", "pending")) }
            SqliteLocalState(context, name).use {
                assertEquals(2, it.read()!!.getInt("revision"))
                assertEquals("pending", it.read()!!.getString("job"))
            }
        } finally { context.deleteDatabase(name) }
    }
    @Test fun upgradeKeepsPayloadAndProvidesAContentOnlyRecoveryExport() {
        val context = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().targetContext
        val name = "migration-${java.util.UUID.randomUUID()}.db"
        val payload = org.json.JSONObject().put("version", 1).put("private_config", "synthetic-key-must-not-export")
            .put("materials", org.json.JSONArray().put(org.json.JSONObject().put("source_ref", "synthetic").put("excerpt", "旧原文")))
        try {
            SqliteLocalState(context, name).use { it.write(payload) }
            SqliteLocalState(context, name, 2).use {
                assertEquals(payload.toString(), it.read().toString())
                org.junit.Assert.assertTrue(it.recoveryText().contains("旧原文"))
                org.junit.Assert.assertFalse(it.recoveryText().contains("synthetic-key"))
                it.clearRecovery()
            }
        } finally { context.deleteDatabase(name) }
    }

}
