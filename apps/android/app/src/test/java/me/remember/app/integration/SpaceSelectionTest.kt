package me.remember.app.integration

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SpaceSelectionTest {
    private val own=JSONObject().put("subject_id","own").put("role","owner")
    private val shared=JSONObject().put("subject_id","shared").put("role","reader")
    @Test fun multipleSpacesRequireChoiceAndNeverAssumeAccountRole() {
        assertNull(initialSpace(listOf(own,shared),null))
        assertSame(shared,initialSpace(listOf(own,shared),"shared"))
        assertSame(own,initialSpace(listOf(own,shared),"own"))
    }
    @Test fun revokedOrDifferentAccountsSavedSpaceCannotRestoreAccess() {
        assertSame(own,initialSpace(listOf(own),"shared"))
        assertNull(initialSpace(listOf(own,shared),"another-account"))
        assertNull(initialSpace(emptyList(),"shared"))
    }
}
