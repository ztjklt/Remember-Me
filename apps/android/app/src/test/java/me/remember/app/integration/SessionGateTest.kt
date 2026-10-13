package me.remember.app.integration

import org.junit.Assert.*
import org.junit.Test

class SessionGateTest {
    @Test fun identityChangeRejectsOldResponsesAndCredentials() {
        val gate = SessionGate()
        val first = gate.connect("http://127.0.0.1:8000", "owner")
        assertTrue(gate.accepts(first))
        val second = gate.connect("http://127.0.0.1:8000", "reader")
        assertFalse(gate.accepts(first))
        assertTrue(gate.accepts(second))
        assertThrows(IllegalStateException::class.java) { gate.requireCurrent(first) }
        gate.clear()
        assertFalse(gate.accepts(second))
    }
    @Test fun switchingSpaceInvalidatesInFlightWorkEvenForSameActor() {
        val gate = SessionGate()
        val first = gate.connect("https://example.org", "credential")
        val next = gate.advance()
        assertFalse(gate.accepts(first))
        assertTrue(gate.accepts(next))
    }
    @Test fun urlValidationRefusesCredentialsQueriesAndPublicCleartext() {
        assertThrows(IllegalArgumentException::class.java) { normalizeServer("http://public.example") }
        assertThrows(IllegalArgumentException::class.java) { normalizeServer("https://user:pass@example.org") }
        assertThrows(IllegalArgumentException::class.java) { normalizeServer("https://example.org/?token=secret") }
        assertEquals("http://10.0.2.2:8000", normalizeServer("http://10.0.2.2:8000/"))
    }
}
