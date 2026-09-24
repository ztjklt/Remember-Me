package me.remember.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import me.remember.app.data.repository.AndroidAudioCaptureService
import me.remember.app.data.repository.EpisodeFlow
import me.remember.app.data.repository.EpisodeMemoryRepository
import me.remember.app.data.repository.HttpEpisodeGateway
import me.remember.app.navigation.RememberMeApp
import me.remember.app.core.designsystem.RememberMeTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val audioCaptureService = AndroidAudioCaptureService(applicationContext)
        val memoryRepository = EpisodeMemoryRepository()
        val episodeFlow = EpisodeFlow(HttpEpisodeGateway(), memoryRepository)
        setContent { RememberMeTheme { RememberMeApp(audioCaptureService, memoryRepository, episodeFlow) } }
    }
}
