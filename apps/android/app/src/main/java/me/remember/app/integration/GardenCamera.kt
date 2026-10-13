package me.remember.app.integration

data class GardenCamera(val zoom: Float = 1f, val x: Float = 0f, val y: Float = 0f)

/** Center-origin camera; a finite scene must keep covering the viewport. */
fun moveGardenCamera(camera: GardenCamera, width: Float, height: Float, panX: Float, panY: Float,
    zoomFactor: Float, anchorX: Float = width / 2, anchorY: Float = height / 2): GardenCamera {
    if(width <= 0 || height <= 0 || !listOf(width, height, panX, panY, zoomFactor, anchorX, anchorY).all { it.isFinite() } || zoomFactor <= 0) return camera
    val zoom = (camera.zoom * zoomFactor).coerceIn(1f, 3f)
    if(zoom == 1f) return GardenCamera()
    val ratio = zoom / camera.zoom
    val x = (anchorX - width / 2) * (1 - ratio) + camera.x * ratio + panX
    val y = (anchorY - height / 2) * (1 - ratio) + camera.y * ratio + panY
    return GardenCamera(zoom, x.coerceIn(-(zoom - 1) * width / 2, (zoom - 1) * width / 2),
        y.coerceIn(-(zoom - 1) * height / 2, (zoom - 1) * height / 2))
}
