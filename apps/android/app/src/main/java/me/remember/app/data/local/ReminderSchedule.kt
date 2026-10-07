package me.remember.app.data.local

import java.time.ZonedDateTime

data class RecordingReminder(val enabled: Boolean = false, val hour: Int = 20, val minute: Int = 0)

internal fun nextRecordingReminder(now: ZonedDateTime, hour: Int, minute: Int): ZonedDateTime {
    require(hour in 0..23 && minute in 0..59)
    val today = now.withHour(hour).withMinute(minute).withSecond(0).withNano(0)
    return if (today.isAfter(now)) today else today.plusDays(1)
}
