package me.remember.app.data.local

import android.Manifest
import android.app.*
import android.content.*
import android.content.pm.PackageManager
import android.os.Build
import me.remember.app.BuildConfig
import me.remember.app.MainActivity
import me.remember.app.R
import java.time.ZonedDateTime

/** User-controlled reminders; no recording, network or model work runs in the receiver. */
class MemoryKeeper(private val context: Context) {
    private val preferences = context.getSharedPreferences("recording-reminder", 0)
    private val notifications = context.getSystemService(NotificationManager::class.java)
    private val alarms = context.getSystemService(AlarmManager::class.java)
    private val channel = "recording-reminders"
    private fun alarmIntent() = PendingIntent.getBroadcast(context, 0,
        Intent(context, MemoryKeeperReceiver::class.java).setAction("me.remember.RECORDING_REMINDER"), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    fun settings() = RecordingReminder(preferences.getBoolean("enabled", false), preferences.getInt("hour", 20), preferences.getInt("minute", 0))
    fun allowed() = (Build.VERSION.SDK_INT < 33 || context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) &&
        notifications.areNotificationsEnabled() && notifications.getNotificationChannel(channel)?.importance != NotificationManager.IMPORTANCE_NONE
    private fun active() = BuildConfig.LOCAL_AGENT_ENABLED && context.getSharedPreferences("execution-mode", 0).getBoolean("local", true)
    fun save(value: RecordingReminder) {
        require(value.hour in 0..23 && value.minute in 0..59) { context.getString(R.string.reminder_invalid_time) }
        check(!value.enabled || allowed()) { context.getString(R.string.reminder_permission_needed) }
        preferences.edit().putBoolean("enabled", value.enabled).putInt("hour", value.hour).putInt("minute", value.minute).apply()
        schedule()
    }
    fun schedule() {
        alarms.cancel(alarmIntent())
        val value = settings()
        if (!active() || !value.enabled || !allowed()) { notifications.cancel(1001); return }
        notifications.createNotificationChannel(NotificationChannel(channel, context.getString(R.string.reminder_channel), NotificationManager.IMPORTANCE_DEFAULT))
        val next = nextRecordingReminder(ZonedDateTime.now(), value.hour, value.minute)
        alarms.setWindow(AlarmManager.RTC_WAKEUP, next.toInstant().toEpochMilli(), 3_600_000, alarmIntent())
    }
    fun notifyNow() {
        if (!active() || !settings().enabled || !allowed()) return
        val date = ZonedDateTime.now().toLocalDate().toString()
        if (preferences.getString("last-date", null) == date) return
        val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        notifications.notify(1001, Notification.Builder(context, channel).setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentTitle(context.getString(R.string.reminder_notification_title)).setContentText(context.getString(R.string.reminder_notification_text))
            .setContentIntent(open).setAutoCancel(true).build())
        preferences.edit().putString("last-date", date).apply()
    }
    fun clear() { preferences.edit().clear().apply(); alarms.cancel(alarmIntent()); notifications.cancel(1001) }
}

class MemoryKeeperReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val keeper = MemoryKeeper(context)
        keeper.schedule()
        if (intent.action == "me.remember.RECORDING_REMINDER") keeper.notifyNow()
    }
}
