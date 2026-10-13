package me.remember.app.integration

enum class ActionPhase { IDLE, RUNNING, SUCCEEDED, FAILED, CANCELLED }

/** A receipt for one client request, never a claim that a queued cloud job finished. */
data class OperationFeedback(val id: Long = 0, val phase: ActionPhase = ActionPhase.IDLE)

internal fun actionPhase(ticket: Long?, operation: OperationFeedback): ActionPhase =
    if(ticket != null && ticket == operation.id) operation.phase else ActionPhase.IDLE

internal data class ActionConfirmation(val message: String, val destructive: Boolean, val action: () -> Unit)
internal typealias ConfirmAction = (String, Boolean, () -> Unit) -> Unit
