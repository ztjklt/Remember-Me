package me.remember.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.getValue
import me.remember.app.core.designsystem.RememberMeTheme
import me.remember.app.data.repository.AndroidAudioCaptureService
import me.remember.app.integration.NativeWorkbenchModel
import me.remember.app.integration.NativeWorkbenchScreen
import me.remember.app.integration.AppearancePreferences
import me.remember.app.integration.ThemeChoice

class MainActivity : ComponentActivity() {
    private lateinit var model: NativeWorkbenchModel
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (android.os.Build.VERSION.SDK_INT == 35) {
            // Android 15 may retain its default content-inset consumer on a
            // preserved window after recreation. Layout flags bypass that
            // consumer; Compose still applies safe insets to interactive content.
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = window.decorView.systemUiVisibility or
                android.view.View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
                android.view.View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
                android.view.View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
        }
        model = ViewModelProvider(this, object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = NativeWorkbenchModel(
                applicationContext, AndroidAudioCaptureService(applicationContext)
            ) as T
        })[NativeWorkbenchModel::class.java]
        val appearance = AppearancePreferences(applicationContext)
        setContent {
            val choice by appearance.choices.collectAsStateWithLifecycle()
            val dark = when(choice.theme) { ThemeChoice.SYSTEM -> isSystemInDarkTheme(); ThemeChoice.LIGHT -> false; ThemeChoice.DARK -> true }
            RememberMeTheme(darkTheme = dark, simpleMode = choice.simpleMode) { NativeWorkbenchScreen(model, choice) { next ->
                runCatching { appearance.update(next) }.onFailure { model.report(it.message ?: "外观设置未保存。") }
            } }
        }
    }
    override fun onStart() { super.onStart(); if (::model.isInitialized) model.onForeground(true) }
    override fun onStop() {
        super.onStop()
        if (::model.isInitialized) {
            if (!isChangingConfigurations) model.onForeground(false)
        }
    }
}
