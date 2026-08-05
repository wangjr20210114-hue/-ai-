package com.floris.android.ui.chat

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

/** Thin adapter over Android's installed speech service; no parallel STT backend. */
internal class VoiceInputController(
    context: Context,
    private val onText: (String) -> Unit,
    private val onListeningChanged: (Boolean) -> Unit,
    private val onUnavailable: () -> Unit,
) : RecognitionListener {

    private val appContext = context.applicationContext
    private val recognizer = if (SpeechRecognizer.isRecognitionAvailable(appContext)) {
        SpeechRecognizer.createSpeechRecognizer(appContext).also { it.setRecognitionListener(this) }
    } else null

    val available: Boolean get() = recognizer != null

    fun start(languageTag: String) {
        val service = recognizer ?: run {
            onUnavailable()
            return
        }
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, languageTag)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }
        onListeningChanged(true)
        runCatching { service.startListening(intent) }
            .onFailure {
                onListeningChanged(false)
                onUnavailable()
            }
    }

    fun stop() {
        runCatching { recognizer?.stopListening() }
        onListeningChanged(false)
    }

    fun release() {
        runCatching { recognizer?.cancel() }
        runCatching { recognizer?.destroy() }
    }

    override fun onPartialResults(partialResults: Bundle?) = publish(partialResults)
    override fun onResults(results: Bundle?) {
        publish(results)
        onListeningChanged(false)
    }

    private fun publish(bundle: Bundle?) {
        bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            ?.firstOrNull()
            ?.trim()
            ?.takeIf { it.isNotEmpty() }
            ?.let(onText)
    }

    override fun onError(error: Int) {
        onListeningChanged(false)
        if (error == SpeechRecognizer.ERROR_CLIENT ||
            error == SpeechRecognizer.ERROR_RECOGNIZER_BUSY ||
            error == SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS
        ) onUnavailable()
    }

    override fun onReadyForSpeech(params: Bundle?) = Unit
    override fun onBeginningOfSpeech() = Unit
    override fun onRmsChanged(rmsdB: Float) = Unit
    override fun onBufferReceived(buffer: ByteArray?) = Unit
    override fun onEndOfSpeech() = Unit
    override fun onEvent(eventType: Int, params: Bundle?) = Unit
}
