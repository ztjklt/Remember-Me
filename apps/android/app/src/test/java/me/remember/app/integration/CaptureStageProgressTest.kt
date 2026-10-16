package me.remember.app.integration

import org.junit.Assert.*
import org.junit.Test

class CaptureStageProgressTest {
    @Test fun transcriptionDoesNotAdvanceWhileServerRemainsInSameStage() {
        assertEquals(50, captureStageProgress("uploaded", false)?.percent)
        assertEquals(50, captureStageProgress("transcribing", false)?.percent)
        assertEquals(100, captureStageProgress("extracting", false)?.percent)
    }
    @Test fun savedTextStartsANewThreeCheckpointFlow() {
        assertEquals(33, captureStageProgress("extracting", true)?.percent)
        assertEquals(67, captureStageProgress("modeling", true)?.percent)
        assertEquals(100, captureStageProgress("ready", true)?.percent)
    }
    @Test fun unknownAndFailedDoNotImplyAnyCompletion() {
        for(reviewed in listOf(true,false)) {
            assertNull(captureStageProgress("failed",reviewed))
            assertNull(captureStageProgress("",reviewed))
            assertNull(captureStageProgress("unrecognized",reviewed))
        }
    }
}
