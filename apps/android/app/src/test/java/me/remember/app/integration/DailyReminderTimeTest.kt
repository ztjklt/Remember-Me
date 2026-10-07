package me.remember.app.integration

import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Instant
import java.time.ZoneId

class DailyReminderTimeTest {
    @Test fun beforeNineUsesTodayInLocalTimezone() {
        assertEquals(Instant.parse("2026-10-08T01:00:00Z"), nextDailyReminder(Instant.parse("2026-10-08T00:30:00Z"), ZoneId.of("Asia/Shanghai")))
    }
    @Test fun atOrAfterNineUsesNextDay() {
        assertEquals(Instant.parse("2026-10-09T01:00:00Z"), nextDailyReminder(Instant.parse("2026-10-08T01:00:00Z"), ZoneId.of("Asia/Shanghai")))
    }
    @Test fun timezoneTransitionKeepsNineLocalRatherThanAddingTwentyFourHours() {
        assertEquals(Instant.parse("2026-11-01T14:00:00Z"), nextDailyReminder(Instant.parse("2026-10-31T15:00:00Z"), ZoneId.of("America/New_York")))
    }
}
