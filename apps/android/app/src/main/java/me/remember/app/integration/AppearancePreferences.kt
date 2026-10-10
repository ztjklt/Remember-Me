package me.remember.app.integration

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import me.remember.app.core.designsystem.NatureScene

enum class ThemeChoice(val title: String) { SYSTEM("跟随系统"), LIGHT("浅色"), DARK("深色") }
enum class SceneChoice(val title: String, val scene: NatureScene?) {
    AUTO("按页面自然场景", null), MEADOW("草地", NatureScene.Meadow), LAKE("湖畔", NatureScene.Lake),
    FOREST("林间", NatureScene.Forest), COAST("海边", NatureScene.Coast)
}
data class AppearanceChoice(val theme: ThemeChoice = ThemeChoice.SYSTEM, val scene: SceneChoice = SceneChoice.AUTO,
    val reduceMotion: Boolean = false)

fun parseAppearance(theme: String?, scene: String?, reduceMotion: Boolean) = AppearanceChoice(
    ThemeChoice.entries.firstOrNull { it.name == theme } ?: ThemeChoice.SYSTEM,
    SceneChoice.entries.firstOrNull { it.name == scene } ?: SceneChoice.AUTO, reduceMotion)

/** Device decoration only. No actor, text, credentials or model settings are stored here. */
class AppearancePreferences(context: Context) {
    private val prefs = context.getSharedPreferences("remember-appearance", Context.MODE_PRIVATE)
    private val state = MutableStateFlow(parseAppearance(prefs.getString("theme", null), prefs.getString("scene", null), prefs.getBoolean("reduce_motion", false)))
    val choices = state.asStateFlow()
    fun update(value: AppearanceChoice) {
        check(prefs.edit().putString("theme", value.theme.name).putString("scene", value.scene.name)
            .putBoolean("reduce_motion", value.reduceMotion).commit()) { "外观设置未保存，请稍后重试。" }
        state.value = value
    }
}
