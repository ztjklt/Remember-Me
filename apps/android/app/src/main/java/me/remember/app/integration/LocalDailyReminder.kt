package me.remember.app.integration

import android.Manifest
import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import me.remember.app.MainActivity
import me.remember.app.R
import java.time.Instant
import java.time.ZoneId

/** Generic, opt-in local notification. This class holds no actor, subject, transcript or network client. */
class LocalDailyReminder(private val context: Context) {
    private val prefs = context.getSharedPreferences("native-local-reminder", Context.MODE_PRIVATE)
    private val alarms get() = context.getSystemService(AlarmManager::class.java)
    private val notifications get() = context.getSystemService(NotificationManager::class.java)
    fun enable() {
        check(canNotify()) { "系统通知权限未授予或已关闭，每日提醒仍保持关闭。" }
        channel()
        check(prefs.edit().putBoolean("enabled", true).commit()) { "无法保存本机提醒设置，请稍后重试。" }
        try { scheduleNext() } catch(error: Exception) { disable(); throw error }
    }
    fun disable() {
        prefs.edit().putBoolean("enabled", false).apply()
        alarms.cancel(alarmIntent())
        notifications.cancel(NOTIFICATION)
    }
    fun deliver() {
        if(!prefs.getBoolean("enabled", false)) return
        if(!canNotify()) { disable(); return }
        channel()
        val open = PendingIntent.getActivity(context, NOTIFICATION,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = Notification.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.rm_brand_mono)
            .setContentTitle("Remember Me · 本机提醒")
            .setContentText("想记下一段故事时，可以打开应用。")
            .setVisibility(Notification.VISIBILITY_PRIVATE)
            .setContentIntent(open).setAutoCancel(true).build()
        notifications.notify(NOTIFICATION, notification)
        scheduleNext()
    }
    private fun canNotify(): Boolean = notifications.areNotificationsEnabled() &&
        (Build.VERSION.SDK_INT < 33 || context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED)
    private fun channel() {
        notifications.createNotificationChannel(NotificationChannel(CHANNEL, "本机每日提醒", NotificationManager.IMPORTANCE_LOW).apply {
            description = "主动开启的通用本机提醒，不包含故事或个人资料，也不调用后端。"
        })
    }
    private fun scheduleNext() {
        // Inexact local alarm: system battery policy may defer delivery; no exact-alarm permission or network worker.
        alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, nextDailyReminder(Instant.now(), ZoneId.systemDefault()).toEpochMilli(), alarmIntent())
    }
    private fun alarmIntent() = PendingIntent.getBroadcast(context, NOTIFICATION,
        Intent(context, DailyReminderReceiver::class.java).setAction(ACTION), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    companion object {
        const val ACTION = "me.remember.app.LOCAL_DAILY_REMINDER"
        private const val CHANNEL = "local-daily-reminder"
        private const val NOTIFICATION = 8877
    }
}

class DailyReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if(intent.action == LocalDailyReminder.ACTION) LocalDailyReminder(context).deliver()
    }
}
