package me.remember.app.integration

import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import java.io.File

class CompanionContractTest {
    @Test fun originalClosesWhenPermissionOrContentChangesButNotWhenModelUseIsAbsent() {
        val original=JSONObject().put("id","n").put("revision",2).put("status","accepted").put("text","原文")
        assertSame(original,retainedContributionOriginal(original,listOf(JSONObject(original.toString()))))
        assertNull(retainedContributionOriginal(original,emptyList()))
        assertNull(retainedContributionOriginal(original,listOf(JSONObject(original.toString()).put("status","withdrawn"))))
        assertNull(retainedContributionOriginal(original,listOf(JSONObject(original.toString()).put("revision",3))))
    }
    @Test fun partialCoverageHintDoesNotPromoteLegacyAnswersOrRepeatExistingNotice() {
        assertNull(personaCoverageHint(JSONObject().put("answer","旧答案")))
        assertNull(personaCoverageHint(JSONObject().put("coverage",JSONObject.NULL)))
        assertNull(personaCoverageHint(JSONObject().put("coverage","complete")))
        assertEquals("已回答有依据的部分",personaCoverageHint(JSONObject().put("coverage","partial").put("omitted_points",2)))
        assertNull(personaCoverageHint(JSONObject().put("coverage","partial").put("answer","正文。已回答有依据的部分。")))
        assertNull(personaCoverageHint(JSONObject().put("coverage","partial").put("answer","正文。部分问题尚未回答。")))
    }
    @Test fun modelPermissionCannotBeChangedBeforeOwnerReviewOrAfterWithdrawal() {
        val note=JSONObject().put("status","pending").put("model_use_author_allowed",false).put("model_use_owner_allowed",false)
        assertFalse(contributionModelUseEditable(note))
        note.put("status","accepted");assertTrue(contributionModelUseEditable(note));assertFalse(contributionModelUseAllowed(note))
        note.put("status","disagreement");assertTrue(contributionModelUseEditable(note))
        listOf("rejected","withdrawn","").forEach{note.put("status",it);assertFalse(contributionModelUseEditable(note))}
    }
    @Test fun savedAudioRetainsRetryKeyAndConfirmedTextAfterRestore() {
        val file=File.createTempFile("companion", ".m4a").apply{writeText("original sound")}
        try {
            val draft=CompanionAudioDraft("letter",file,key="stable-key",remote=JSONObject().put("audio_id","audio-one").put("status","confirmed").put("reviewed_text","核对稿"))
            val restored=restoredCompanionAudio(JSONObject(draft.saved().toString()))!!
            assertEquals("stable-key",restored.key);assertEquals("核对稿",restored.remote!!.text("reviewed_text"));assertEquals(file,restored.file)
            assertNull(restoredCompanionAudio(draft.saved().put("purpose","episode")))
            file.delete();assertNull(restoredCompanionAudio(draft.saved()))
        } finally {file.delete()}
    }
    @Test fun unuploadedOrUnreviewedAudioCannotSilentlyBecomeTextOnlyContribution() {
        val draft=CompanionAudioDraft("contribution",File("test.m4a"))
        assertThrows(IllegalArgumentException::class.java) {companionPayload("正文",draft)}
        assertThrows(IllegalArgumentException::class.java) {companionPayload("正文",draft.copy(remote=JSONObject().put("status","reviewing").put("audio_id","audio-1")))}
        val body=companionPayload("正文",draft.copy(remote=JSONObject().put("status","confirmed").put("audio_id","audio-1")),listOf("story-a","story-a"))
        assertEquals("audio-1",body.getString("audio_id"));assertEquals(1,body.getJSONArray("narrative_ids").length())
        assertFalse(body.has("model_use_author_allowed"));assertFalse(body.has("model_use_owner_allowed"));assertFalse(body.has("author_actor_id"))
    }
    @Test fun modelUseNeedsBothIndependentPermissionsEvenAfterAcceptance() {
        val note=JSONObject().put("status","accepted").put("model_use_author_allowed",true)
        assertFalse(contributionModelUseAllowed(note))
        note.put("model_use_owner_allowed",true);assertTrue(contributionModelUseAllowed(note))
        note.put("model_use_author_allowed",false);assertFalse(contributionModelUseAllowed(note))
    }
    @Test fun companionDiscoveryDoesNotDowngradeAnExistingOwner() {
        val owner=JSONObject().put("subject_id","same").put("role","owner")
        val companion=JSONObject().put("subject_id","same").put("role","companion")
        val only=JSONObject().put("subject_id","letter-only").put("role","companion")
        val spaces=mergeCompanionSpaces(listOf(owner),listOf(companion,only))
        assertEquals(2,spaces.size);assertEquals("owner",spaces.first{it.text("subject_id")=="same"}.text("role"))
    }
    @Test fun understandingOverviewExcludesUnconfirmedAndStaleCandidates() {
        val data=JSONObject().put("understandings",JSONArray(listOf("confirmed","pending","stale","rejected").map{JSONObject().put("status",it)}))
        assertEquals(1,confirmedUnderstandings(data).size)
    }
}
