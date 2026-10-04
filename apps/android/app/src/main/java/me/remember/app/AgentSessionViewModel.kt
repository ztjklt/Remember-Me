package me.remember.app

import androidx.lifecycle.ViewModel
import me.remember.app.data.repository.AgentRepository
import me.remember.app.data.repository.HttpAgentGateway

/** Retain the in-memory credential and Agent session across Activity recreation. */
class AgentSessionViewModel : ViewModel() {
    val repository = AgentRepository(HttpAgentGateway())
}
