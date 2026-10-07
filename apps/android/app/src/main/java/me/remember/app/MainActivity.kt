package me.remember.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.data.repository.AndroidAudioCaptureService
import me.remember.app.integration.NativeWorkbenchModel
import me.remember.app.integration.NativeWorkbenchScreen

class MainActivity : ComponentActivity() {
    private lateinit var model: NativeWorkbenchModel
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        model = ViewModelProvider(this, object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = NativeWorkbenchModel(
                applicationContext, AndroidAudioCaptureService(applicationContext)
            ) as T
        })[NativeWorkbenchModel::class.java]
        setContent { RememberMeTheme { NativeWorkbenchScreen(model) } }
    }
    override fun onStart() { super.onStart(); if (::model.isInitialized) model.onForeground(true) }
    override fun onStop() {
        super.onStop()
        if (::model.isInitialized) {
            if (!isChangingConfigurations) model.onForeground(false)
        }
    }
}
