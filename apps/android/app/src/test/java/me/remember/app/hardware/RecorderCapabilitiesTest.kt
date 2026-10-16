package me.remember.app.hardware

import org.junit.Assert.*
import org.junit.Test

class RecorderCapabilitiesTest {
    @Test fun activeRecordingOnlyAllowsPauseAndResume() {
        assertTrue(recorderCommandAllowed(RecorderCommand.PAUSE, DeviceRecordPhase.RECORDING, false, true))
        assertFalse(recorderCommandAllowed(RecorderCommand.RESUME, DeviceRecordPhase.IDLE, false, false))
        for (command in listOf(RecorderCommand.OTA, RecorderCommand.DELETE_RECORDING, RecorderCommand.RESET, RecorderCommand.UNBIND)) {
            assertFalse(recorderCommandAllowed(command, DeviceRecordPhase.RECORDING, false, false))
            assertFalse(recorderCommandAllowed(command, DeviceRecordPhase.IDLE, false, true))
        }
    }
}
