package me.remember.app.integration

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class MemoryMapTest {
    private fun row(id:String,status:String,facet:String,valid:Boolean=true)=JSONObject().put("id",id)
        .put("status",status).put("source_valid",valid).put("facets",JSONArray().put(facet))
        .put("title",id).put("text","有来源的内容")
    private val rows=listOf(row("approved","confirmed","EXPERIENCE"),row("draft","pending","WISHES"),
        row("stale","stale","WISHES",false),row("revoked","confirmed","WISHES",false))
    @Test fun countsNeverMixPendingAndValidConfirmed() {
        assertEquals(0 to 1,memoryFacetCounts(rows,"WISHES",true))
        assertEquals(0 to 0,memoryFacetCounts(rows,"WISHES",false))
    }
    @Test fun draftFiltersStillRespectViewAndRole() {
        assertEquals(listOf("draft","stale"),selectNarrativeRecords(rows,true,true,2,"WISHES","").map{it.getString("id")})
        assertTrue(selectNarrativeRecords(rows,true,true,0,"","").isEmpty())
        assertTrue(selectNarrativeRecords(rows,false,true,2,"","").isEmpty())
    }
    @Test fun revocationRemovesProjectedContent() {
        assertTrue(selectNarrativeRecords(rows,false,false,2,"","").isEmpty())
        assertEquals(listOf("approved"),selectNarrativeRecords(rows,false,false,0,"","approved").map{it.getString("id")})
    }
    @Test fun peopleAppearBeforeRelatedStories() {
        val samples=listOf(row("story","pending","RELATIONSHIPS").put("kind","story"),
            row("person","pending","RELATIONSHIPS").put("kind","person"))
        assertEquals(listOf("person","story"),selectNarrativeRecords(samples,true,true,1,"","").map{it.getString("id")})
    }
    @Test fun allSidesDoesNotSilentlyExcludeAnotherView() {
        assertEquals(listOf("approved"),selectNarrativeRecords(rows,false,false,-1,"","").map{it.getString("id")})
    }
    @Test fun exactSearchIncludesEvidenceButNeverStaleSource() {
        val cited=row("cited","confirmed","EXPERIENCE").put("evidence",JSONArray().put(JSONObject().put("excerpt","这个杯子不是陈岚送的")))
        val revoked=row("hidden","confirmed","EXPERIENCE",false).put("evidence",cited.getJSONArray("evidence"))
        assertEquals(listOf("cited"),selectNarrativeRecords(listOf(cited,revoked),false,false,0,"","陈岚").map{it.getString("id")})
    }
}
