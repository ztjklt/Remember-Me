package me.remember.app.data.local

import java.time.ZonedDateTime
import org.junit.Assert.*
import org.junit.Test

class ReminderScheduleTest {
    @Test fun futureTimeUsesTodayAndElapsedTimeUsesTomorrow() {
        val morning = ZonedDateTime.parse("2026-10-07T10:00:00+08:00[Asia/Shanghai]")
        assertEquals("2026-10-07T20:00+08:00[Asia/Shanghai]", nextRecordingReminder(morning, 20, 0).toString())
        assertEquals(8, nextRecordingReminder(morning.withHour(20), 20, 0).dayOfMonth)
    }
    @Test fun nextDayKeepsLocalTimeAcrossDaylightSavingChange() {
        val before = ZonedDateTime.parse("2026-03-07T21:00:00-05:00[America/New_York]")
        val next = nextRecordingReminder(before, 20, 0)
        assertEquals(20, next.hour); assertEquals(-4 * 3600, next.offset.totalSeconds)
        assertEquals(22 * 3600, java.time.Duration.between(before, next).seconds)
    }
    @Test fun invalidTimeIsRejected() {
        try { nextRecordingReminder(ZonedDateTime.now(), 24, 0); fail("invalid hour") } catch (_: IllegalArgumentException) {}
    }
}
