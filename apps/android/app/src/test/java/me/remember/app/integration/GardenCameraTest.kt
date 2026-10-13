package me.remember.app.integration

import org.junit.Assert.*
import org.junit.Test

class GardenCameraTest {
    @Test fun zoomKeepsTheTouchedWorldPointUnderTheFinger() {
        val old = GardenCamera(1.5f, 10f, 20f)
        val next = moveGardenCamera(old, 360f, 420f, 0f, 0f, 1.2f, 220f, 240f)
        assertEquals(1.8f, next.zoom, .001f)
        assertEquals((220 - 180 - old.x) / old.zoom, (220 - 180 - next.x) / next.zoom, .001f)
        assertEquals((240 - 210 - old.y) / old.zoom, (240 - 210 - next.y) / next.zoom, .001f)
    }
    @Test fun draggingCannotExposeBeyondTheFiniteScene() {
        val next = moveGardenCamera(GardenCamera(2f), 360f, 420f, 999f, -999f, 1f)
        assertEquals(180f, next.x, .001f)
        assertEquals(-210f, next.y, .001f)
    }
    @Test fun ReturningToOneHundredPercentRemovesHiddenPan() {
        assertEquals(GardenCamera(), moveGardenCamera(GardenCamera(2f, 30f, -50f), 360f, 420f, 0f, 0f, .1f))
    }
    @Test fun maximumZoomIsBoundedAndInvalidGeometryKeepsTheCurrentState() {
        assertEquals(3f, moveGardenCamera(GardenCamera(), 360f, 420f, 0f, 0f, 99f).zoom, .001f)
        val old = GardenCamera(1.4f, 0f, 0f)
        assertEquals(old, moveGardenCamera(old, 0f, 420f, 0f, 0f, 1.2f))
        assertEquals(old, moveGardenCamera(old, 360f, 420f, 0f, 0f, Float.NaN))
    }
}
