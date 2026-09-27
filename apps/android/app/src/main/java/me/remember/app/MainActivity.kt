package me.remember.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.data.repository.AndroidAudioCaptureService
import me.remember.app.data.repository.AndroidSherpaOnnxAsrService
import me.remember.app.feature.MobileViewModel
import me.remember.app.navigation.RememberMeApp

class MainActivity : ComponentActivity() {
    private lateinit var model: MobileViewModel
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        model = ViewModelProvider(this, object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = MobileViewModel(
                AndroidAudioCaptureService(applicationContext), AndroidSherpaOnnxAsrService(applicationContext)
                // Backend processing is deliberately unconfigured until its integration is approved.
            ) as T
        })[MobileViewModel::class.java]
        setContent { RememberMeTheme { RememberMeApp(model) } }
    }
    override fun onStop() {
        super.onStop()
        if (::model.isInitialized) {
            if (!isChangingConfigurations) model.finish()
            model.audio.stopPlayback()
        }
    }
}
