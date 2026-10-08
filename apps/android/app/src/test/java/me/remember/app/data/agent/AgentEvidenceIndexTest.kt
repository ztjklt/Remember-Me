package me.remember.app.data.agent

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class AgentEvidenceIndexTest {
    private fun source(id: String, text: String, type: String = "SUBJECT") = JSONObject().put("evidence_id", id)
        .put("excerpt", text).put("context", "").put("source_type", type).put("source_ref", "episode:$id")
        .put("observed_at", "2026-10-08T00:00:00Z").put("episode_id", id)
    @Test fun teammateEnumerationIsNotLimitedToTopKAndThirdPartyDoesNotEnterThePack() {
        val sources = JSONArray((1..16).map { source("ev_$it", "队友同学$it，专业计算机。") })
            .put(source("excluded", "队友资料不可用", "THIRD_PARTY"))
        val pack = AgentEvidenceIndex(sources).retrieve("我有几个队友，都是什么专业？")
        assertEquals(16, pack.length()); assertFalse(pack.objects().any { it.getString("evidence_id") == "excluded" })
    }
    @Test fun nameCorrectionAndItsOriginalEvidenceAreRetrievedTogether() {
        val original = source("ev_old", "我是林晨，我在大学读研。")
        val correction = source("cev_name", "名字是林宸", "CALIBRATION").put("related_evidence_ids", JSONArray().put("ev_old"))
        val pack = AgentEvidenceIndex(JSONArray(listOf(original, correction))).retrieve("我的姓名是什么？")
        assertEquals(setOf("ev_old", "cev_name"), pack.objects().map { it.getString("evidence_id") }.toSet())
    }
    @Test fun anOldEventCanBeLocatedInLongHistoryWithoutTruncatingItsSpan() {
        val sources = JSONArray((1..20).map { source("filler_$it", "无关材料。".repeat(1000)) })
            .put(source("old", "旧事件记录。".repeat(1000) + "我在北海参加帆船比赛。" + "无关段落。".repeat(1000)))
        val pack = AgentEvidenceIndex(sources).retrieve("北海帆船比赛发生了什么？")
        assertTrue(pack.objects().any { it.getString("excerpt").contains("我在北海参加帆船比赛。") })
        assertTrue(pack.objects().all { parentId(it) == "old" })
        val span = pack.getJSONObject(0)
        assertTrue(span.getString("source_ref").contains("#span:")); assertTrue("old" in answerRoots(JSONObject()
            .put("evidence_ids", JSONArray().put(span.getString("evidence_id"))).put("evidence", pack)))
    }
    @Test fun overlyLargeRelevantEnumerationIsRejectedRatherThanSilentlyReduced() {
        val sources = JSONArray((1..20).map { source("ev_$it", "队友及专业。".repeat(1000)) })
        try { AgentEvidenceIndex(sources).retrieve("全部队友是什么专业？"); fail("partial count accepted") }
        catch (e: IllegalArgumentException) { assertTrue(e.message!!.contains("未压缩或截断")) }
    }
}
