package me.remember.app.data.repository

/**
 * Adapter boundary for sherpa-onnx. The concrete recognizer is created after the
 * selected sherpa model and JNI/AAR are bundled into the Android app.
 */
class SherpaOnnxAsrService(
    private val recognizer: suspend (audioPath: String) -> String
) : LocalAsrService {
    override suspend fun transcribe(audioRef: String): String = recognizer(audioRef)
}
