package me.remember.app.integration

import org.json.JSONObject

/** A role is scoped to a space, never inferred from the account's display name. */
internal fun initialSpace(spaces: List<JSONObject>, savedSubject: String?): JSONObject? =
    spaces.firstOrNull { it.text("subject_id") == savedSubject } ?: spaces.singleOrNull()
