package me.remember.app.data.agent

import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class MemoryObservationTest {
    private fun source() = JSONObject().put("evidence_id", "ev_one").put("source_type", "SUBJECT")
        .put("excerpt", "😀我是小林。我在读研。昨天我紧张，散步后平静了。").put("observed_at", "2026-10-08T10:00:00Z")
    private fun observation() = JSONObject().put("dimension", "identity").put("summary", "本人自述姓名小林")
        .put("quote", "我是小林").put("event_time", JSONObject.NULL).put("time_text", "").put("certainty", "REPORTED")
        .put("attributes", JSONObject().put("facet", "NAME").put("entity", "本人").put("value", "小林"))
    private fun worker(item: JSONObject) = MemoryObservationExtractor(object : StructuredAgentModel {
        override val modelVersion = "synthetic-model"
        override suspend fun complete(prompt: String, input: JSONObject) = JSONObject().put("observations", JSONArray().put(item))
    })
    @Test fun unicodeSpansAreCodePointsAndStableAcrossRetries() = runBlocking {
        val worker = worker(observation()); val enabled = setOf("identity")
        val first = worker.extract(source(), 0, enabled).getJSONObject(0)
        assertEquals(1, first.getInt("start")); assertEquals(5, first.getInt("end"))
        assertEquals(first.getString("observation_id"), worker.extract(source(), 0, enabled).getJSONObject(0).getString("observation_id"))
        assertEquals(MemoryDimensionRegistry.version, first.getString("taxonomy_version"))
    }
    @Test fun inventedQuotesAndUnsupportedAudioAttributesAreRejected() = runBlocking {
        for (item in listOf(observation().put("quote", "我是不存在的人"),
            observation().put("dimension", "vocal_state").put("attributes", JSONObject().put("state", "疲惫").put("channel", "AUDIO")))) {
            try { worker(item).extract(source(), 0, setOf("identity", "vocal_state")); fail("invalid observation accepted") }
            catch (_: IllegalArgumentException) {}
        }
    }
    @Test fun eventDateRequiresAnOriginalTimeExpression() = runBlocking {
        try { worker(observation().put("event_time", "2026-10-08")).extract(source(), 0, setOf("identity")); fail("date guessed") }
        catch (_: IllegalArgumentException) {}
        val mood = observation().put("dimension", "mood").put("quote", "昨天我紧张")
            .put("event_time", "2026-10-07").put("time_text", "昨天")
            .put("attributes", JSONObject().put("emotion", "紧张").put("time_scope", "EVENT").put("valence", "NEGATIVE"))
        assertEquals("2026-10-07", worker(mood).extract(source(), 0, setOf("mood")).getJSONObject(0).getString("event_time"))
    }
    @Test fun longSourcesArePartitionedWithoutLosingSurrogatePairsOrText() {
        val text = "字".repeat(5999) + "😀" + "后文".repeat(5000)
        val parts = mutableListOf<String>(); var offset = 0
        while (offset < text.length) { val part = sourceChunk(text, offset); parts.add(part); offset += part.length }
        assertEquals(text, parts.joinToString("")); assertFalse(parts.any { it.last().isHighSurrogate() || it.first().isLowSurrogate() })
    }
    @Test fun timeExpressionCanPrecedeTheMoodQuoteAndRetainsItsOwnCodePointSpan() = runBlocking {
        val mood = observation().put("dimension", "mood").put("quote", "我紧张")
            .put("event_time", "2026-10-07").put("time_text", "昨天")
            .put("attributes", JSONObject().put("emotion", "紧张").put("time_scope", "EVENT").put("valence", "NEGATIVE"))
        val result = worker(mood).extract(source(), 0, setOf("mood")).getJSONObject(0)
        assertEquals(11, result.getInt("time_start")); assertEquals(13, result.getInt("time_end"))
    }
    @Test fun nameCorrectionCannotReplaceAnEducationObservation() = runBlocking {
        val old = observation().put("observation_id", "old_school").put("evidence_id", "ev_school")
            .put("attributes", JSONObject().put("facet", "EDUCATION").put("entity", "本人").put("value", "读研"))
        val correction = source().put("source_type", "CALIBRATION")
        try { worker(observation().put("replaces", JSONArray().put("old_school")))
            .extract(correction, 0, setOf("identity"), JSONArray().put(old)); fail("school erased") }
        catch (_: IllegalArgumentException) {}
    }
}
