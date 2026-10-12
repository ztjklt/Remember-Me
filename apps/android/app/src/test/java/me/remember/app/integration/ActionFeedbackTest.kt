package me.remember.app.integration

import org.junit.Assert.assertEquals
import org.junit.Test

class ActionFeedbackTest {
    @Test fun unrelatedCompletionNeverTurnsAnEarlierButtonGreen() {
        assertEquals(ActionPhase.IDLE, actionPhase(12, OperationFeedback(13, ActionPhase.SUCCEEDED)))
        assertEquals(ActionPhase.IDLE, actionPhase(null, OperationFeedback(13, ActionPhase.SUCCEEDED)))
    }

    @Test fun requestMustFinishBeforeSuccessAndFailuresStayFailures() {
        assertEquals(ActionPhase.RUNNING, actionPhase(12, OperationFeedback(12, ActionPhase.RUNNING)))
        assertEquals(ActionPhase.FAILED, actionPhase(12, OperationFeedback(12, ActionPhase.FAILED)))
        assertEquals(ActionPhase.SUCCEEDED, actionPhase(12, OperationFeedback(12, ActionPhase.SUCCEEDED)))
    }

    @Test fun identityResetClearsFeedbackEvenIfAButtonWasWaiting() {
        assertEquals(ActionPhase.IDLE, actionPhase(12, OperationFeedback()))
    }
}
