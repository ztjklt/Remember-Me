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
}
