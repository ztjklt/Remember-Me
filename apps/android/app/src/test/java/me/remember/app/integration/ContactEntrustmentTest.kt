package me.remember.app.integration

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ContactEntrustmentTest {
    @Test fun selectedContentUsesBothTypeAndIdAndDoesNotSendTranscriptsOrStoragePaths() {
        val episode=JSONObject().put("kind","episode").put("id","same").put("text","private").put("object_key","secret")
        val dedicated=JSONObject().put("kind","dedicated").put("id","same")
        val selection=contactSelection(listOf(episode,dedicated),setOf("dedicated:same"))
        assertEquals(1,selection.getJSONArray("sources").length())
        assertEquals("dedicated",selection.getJSONArray("sources").getJSONObject(0).getString("kind"))
        assertFalse(selection.toString().contains("private"))
        assertFalse(selection.toString().contains("secret"))
    }
    @Test fun providerAcknowledgementNeverBecomesClaimedOrOpened() {
        val plan=JSONObject().put("status","active").put("notice_status","accepted")
        assertEquals("通知已提交，待领取",contactPlanStatus(plan))
        plan.put("claimed_at","2026-10-17T00:00:00Z")
        assertEquals("已验证领取",contactPlanStatus(plan))
        plan.put("opened_at","2026-10-17T00:01:00Z").put("status","revoked")
        assertEquals("已撤销",contactPlanStatus(plan))
    }
}
