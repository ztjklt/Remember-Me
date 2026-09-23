package me.remember.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import me.remember.app.data.repository.PhoneMicrophoneCaptureAdapter
import me.remember.app.data.repository.SelectingAudioCaptureService
import me.remember.app.data.repository.MemoryRepository
import me.remember.app.data.mock.MockRememberMeRepository
import me.remember.app.navigation.RememberMeApp
import me.remember.app.core.designsystem.RememberMeTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val phoneFallbackAdapter = PhoneMicrophoneCaptureAdapter(applicationContext)
        val audioCaptureService = SelectingAudioCaptureService(phoneFallbackAdapter)
        val memoryRepository: MemoryRepository = MockRememberMeRepository()
        setContent { RememberMeTheme { RememberMeApp(audioCaptureService, memoryRepository) } }
    }
}
