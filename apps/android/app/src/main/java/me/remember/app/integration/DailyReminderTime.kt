package me.remember.app.integration

import java.time.Instant
import java.time.ZoneId

fun nextDailyReminder(now: Instant, zone: ZoneId): Instant {
    val today = now.atZone(zone).withHour(9).withMinute(0).withSecond(0).withNano(0)
    return (if(today.toInstant().isAfter(now)) today else today.plusDays(1)).toInstant()
}
