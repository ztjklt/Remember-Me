package me.remember.app.feature

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.res.stringResource
import me.remember.app.LocalAgentSession
import me.remember.app.R
import me.remember.app.data.local.RecordingReminder

@Composable
fun ReminderSettings(session: LocalAgentSession) {
    val current = session.reminder
    var enabled by rememberSaveable(current.enabled) { mutableStateOf(current.enabled) }
    var time by rememberSaveable(current.hour, current.minute) { mutableStateOf("%02d:%02d".format(current.hour, current.minute)) }
    var error by remember { mutableStateOf(false) }
    var pending by remember { mutableStateOf<RecordingReminder?>(null) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        pending?.let { session.saveReminder(it) }; pending = null
    }
    Text(stringResource(R.string.reminder_title), style = MaterialTheme.typography.titleLarge)
    Text(stringResource(R.string.reminder_explanation))
    Row { Checkbox(enabled, { enabled = it }); Text(stringResource(R.string.reminder_enable)) }
    OutlinedTextField(time, { time = it; error = false }, label = { Text(stringResource(R.string.reminder_time)) }, singleLine = true, isError = error)
    if (error) Text(stringResource(R.string.reminder_invalid_time), color = MaterialTheme.colorScheme.error)
    Button({
        val parts = time.split(":").map { it.toIntOrNull() }
        val hour = parts.getOrNull(0); val minute = parts.getOrNull(1)
        if (parts.size != 2 || hour == null || minute == null || hour !in 0..23 || minute !in 0..59) error = true
        else {
            val value = RecordingReminder(enabled, hour, minute)
            if (enabled && Build.VERSION.SDK_INT >= 33 && !session.reminderAllowed()) {
                pending = value; permission.launch(Manifest.permission.POST_NOTIFICATIONS)
            } else session.saveReminder(value)
        }
    }) { Text(stringResource(R.string.reminder_save)) }
}
