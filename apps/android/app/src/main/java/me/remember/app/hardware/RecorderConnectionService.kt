package me.remember.app.hardware

import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import me.remember.app.MainActivity

/** User-started connected-device session. This service never opens a microphone. */
class RecorderConnectionService : Service() {
    private val jobs = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var observation: Job? = null
    private var owned: Work3200Controller? = null
    private var ownedGeneration = -1L
    override fun onBind(intent: Intent?): IBinder? = null
    override fun onCreate() {
        super.onCreate()
        // A failed grant can release the controller before onStartCommand.
        // Fulfil Android's foreground-start obligation even for that cancelled
        // start; otherwise it kills the app after the foreground deadline.
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "录音豆连接", NotificationManager.IMPORTANCE_LOW))
        val initial = notification("正在连接录音豆")
        if (Build.VERSION.SDK_INT >= 29) startForeground(ID, initial, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        else startForeground(ID, initial)
        instance = this
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "disconnect") { active?.disconnect(); stopSelf(); return START_NOT_STICKY }
        val controller = active ?: run { stopSelf(); return START_NOT_STICKY }
        owned = controller
        ownedGeneration = generation
        val manager = getSystemService(NotificationManager::class.java)
        observation?.cancel()
        observation = jobs.launch {
            controller.ui.map { state -> when {
                state.recordPhase == DeviceRecordPhase.RECORDING -> "录音豆正在录音 · ${state.elapsedMs / 1000} 秒"
                state.recordPhase == DeviceRecordPhase.PAUSED -> "录音豆已暂停 · ${state.elapsedMs / 1000} 秒"
                state.busy == "download" -> "同步录音到手机 ${state.percent?.let { "$it%" }.orEmpty()}"
                state.connected -> "录音豆已连接，按设备按钮开始录音"
                else -> state.message
            } }.distinctUntilChanged().collect { manager.notify(ID, notification(it)) }
        }
        return START_NOT_STICKY
    }
    private fun notification(text: String): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val stop = PendingIntent.getService(this, 1, Intent(this, RecorderConnectionService::class.java).setAction("disconnect"), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        return Notification.Builder(this, CHANNEL).setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentTitle("勿忘我 · 录音豆").setContentText(text).setContentIntent(open)
            .setOngoing(true).setOnlyAlertOnce(true).addAction(Notification.Action.Builder(null, "断开连接", stop).build()).build()
    }
    override fun onDestroy() {
        if(instance === this) instance = null
        jobs.cancel()
        val controller = owned
        if (active === controller && ownedGeneration == generation) { active = null; controller?.disconnect("设备连接服务已结束，录音状态待重新确认。") }
        super.onDestroy()
    }
    companion object {
        private const val CHANNEL = "recorder-connection"
        private const val ID = 3200
        private var active: Work3200Controller? = null
        private var instance: RecorderConnectionService? = null
        private var generation = 0L
        fun start(context: Context, controller: Work3200Controller) {
            if (active != null && active !== controller) active?.disconnect()
            active = controller
            generation++
            try { context.startForegroundService(Intent(context, RecorderConnectionService::class.java)) }
            catch (error: Exception) { active = null; throw error }
        }
        fun release(context: Context, controller: Work3200Controller) {
            if (active === controller) {
                active = null
                // stopService before onCreate can cancel a pending foreground
                // start and make Android kill the process immediately. If it
                // has not been created, let onCreate promote, then onStartCommand
                // observe the released owner and stop itself safely.
                instance?.stopSelf()
            }
        }
    }
}
