package me.remember.app.data.repository

import android.content.Context
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.OfflineModelConfig
import com.k2fsa.sherpa.onnx.OfflineParaformerModelConfig
import com.k2fsa.sherpa.onnx.OfflineRecognizer
import com.k2fsa.sherpa.onnx.OfflineRecognizerConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.nio.ByteOrder
import kotlin.math.roundToInt

class AndroidSherpaOnnxAsrService(private val context: Context) : LocalAsrService {
    override suspend fun transcribe(audioRef: String): String = withContext(Dispatchers.Default) {
        val samples = decodeToMono16k(File(audioRef))
        require(samples.isNotEmpty()) { "The recording contains no decodable audio." }
        val model = OfflineParaformerModelConfig().apply { model = "paraformer/model.int8.onnx" }
        val modelConfig = OfflineModelConfig().apply {
            paraformer = model
            tokens = "paraformer/tokens.txt"
            numThreads = 2
            provider = "cpu"
        }
        val config = OfflineRecognizerConfig().apply {
            featConfig = FeatureConfig().apply {
                sampleRate = TARGET_SAMPLE_RATE
                featureDim = 80
            }
            this.modelConfig = modelConfig
            decodingMethod = "greedy_search"
        }
        val recognizer = OfflineRecognizer(context.assets, config)
        try {
            val stream = recognizer.createStream()
            stream.acceptWaveform(samples, TARGET_SAMPLE_RATE)
            recognizer.decode(stream)
            recognizer.getResult(stream).text.trim()
        } finally {
            recognizer.release()
        }
    }

    private fun decodeToMono16k(file: File): FloatArray {
        require(file.isFile) { "Audio file does not exist." }
        val extractor = MediaExtractor()
        extractor.setDataSource(file.absolutePath)
        val track = (0 until extractor.trackCount).firstOrNull { extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true }
            ?: error("No audio track found.")
        extractor.selectTrack(track)
        val format = extractor.getTrackFormat(track)
        val mime = format.getString(MediaFormat.KEY_MIME) ?: error("Audio MIME type is missing.")
        val sourceRate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
        val sourceChannels = format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
        val decoder = MediaCodec.createDecoderByType(mime)
        decoder.configure(format, null, null, 0)
        decoder.start()
        val pcm = ArrayList<Float>()
        val info = MediaCodec.BufferInfo()
        var inputDone = false
        var outputDone = false
        try {
            while (!outputDone) {
                if (!inputDone) {
                    val index = decoder.dequeueInputBuffer(TIMEOUT_US)
                    if (index >= 0) {
                        val input = decoder.getInputBuffer(index) ?: error("Decoder input unavailable.")
                        val size = extractor.readSampleData(input, 0)
                        if (size < 0) {
                            decoder.queueInputBuffer(index, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                            inputDone = true
                        } else {
                            decoder.queueInputBuffer(index, 0, size, extractor.sampleTime, 0)
                            extractor.advance()
                        }
                    }
                }
                when (val index = decoder.dequeueOutputBuffer(info, TIMEOUT_US)) {
                    MediaCodec.INFO_OUTPUT_FORMAT_CHANGED, MediaCodec.INFO_TRY_AGAIN_LATER -> Unit
                    else -> if (index >= 0) {
                        val output = decoder.getOutputBuffer(index)
                        if (output != null && info.size > 0) {
                            output.position(info.offset)
                            output.limit(info.offset + info.size)
                            val bytes = ByteArray(output.remaining()).also(output::get)
                            val buffer = java.nio.ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer()
                            while (buffer.hasRemaining()) {
                                var mixed = 0f
                                repeat(sourceChannels) { if (buffer.hasRemaining()) mixed += buffer.get() / 32768f }
                                pcm += mixed / sourceChannels
                            }
                        }
                        decoder.releaseOutputBuffer(index, false)
                        if ((info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) outputDone = true
                    }
                }
            }
        } finally {
            runCatching { decoder.stop() }
            decoder.release()
            extractor.release()
        }
        if (sourceRate == TARGET_SAMPLE_RATE) return pcm.toFloatArray()
        val outputSize = (pcm.size.toDouble() * TARGET_SAMPLE_RATE / sourceRate).roundToInt()
        return FloatArray(outputSize) { i ->
            val sourceIndex = i.toDouble() * sourceRate / TARGET_SAMPLE_RATE
            val left = sourceIndex.toInt().coerceIn(0, pcm.lastIndex)
            val right = (left + 1).coerceIn(0, pcm.lastIndex)
            val fraction = (sourceIndex - left).toFloat()
            pcm[left] * (1f - fraction) + pcm[right] * fraction
        }
    }

    companion object { private const val TARGET_SAMPLE_RATE = 16_000; private const val TIMEOUT_US = 10_000L }
}
