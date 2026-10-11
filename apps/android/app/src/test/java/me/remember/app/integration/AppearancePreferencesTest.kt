package me.remember.app.integration

import org.junit.Assert.*
import org.junit.Test

class AppearancePreferencesTest {
    @Test fun unknownStoredValuesUseSystemAndPageDefaults() {
        assertEquals(ThemeChoice.SYSTEM, parseAppearance("removed-theme", "unknown-scene", false).theme)
        assertEquals(SceneChoice.AUTO, parseAppearance("removed-theme", "unknown-scene", false).scene)
    }
    @Test fun persistedChoicesPreserveExplicitThemeSceneAndReducedMotion() {
        val parsed = parseAppearance("DARK", "LAKE", true)
        assertEquals(ThemeChoice.DARK, parsed.theme)
        assertEquals(SceneChoice.LAKE, parsed.scene)
        assertTrue(parsed.reduceMotion)
    }
    @Test fun simpleModeIsOptInAndIndependentOfThemeAndMotion() {
        assertFalse(parseAppearance(null, null, false).simpleMode)
        val simple = parseAppearance("DARK", "FOREST", false, true)
        assertTrue(simple.simpleMode)
        assertEquals(ThemeChoice.DARK, simple.theme)
        assertEquals(SceneChoice.FOREST, simple.scene)
        assertFalse(simple.reduceMotion)
        assertEquals(simple.copy(simpleMode = false), parseAppearance("DARK", "FOREST", false))
    }
}
