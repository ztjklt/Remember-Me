package me.remember.app

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import me.remember.app.data.repository.AudioRecording

/** Activity-scoped handoff; process death falls back to the recording library. */
class CaptureFlowViewModel : ViewModel() {
    var recording by mutableStateOf<AudioRecording?>(null)
}
