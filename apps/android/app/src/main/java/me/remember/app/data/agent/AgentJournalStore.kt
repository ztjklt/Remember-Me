package me.remember.app.data.agent

import org.json.JSONObject

/** Writes publish the whole journal atomically. Implementations must never silently reset unreadable data. */
interface AgentJournalStore {
    fun read(): JSONObject?
    fun write(state: JSONObject)
}
