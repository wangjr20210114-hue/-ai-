package com.floris.android.core.network

/**
 * Small reusable retry schedule for idempotent network reconciliation.
 *
 * The caller still owns retry policy and cancellation; this class only spaces
 * attempts so a durable operation such as stop confirmation does not busy-poll
 * Maker while the device is offline.
 */
class ExponentialBackoff(
    private val initialDelayMillis: Long,
    private val maximumDelayMillis: Long,
    private val multiplier: Double = 2.0,
) {
    init {
        require(initialDelayMillis > 0)
        require(maximumDelayMillis >= initialDelayMillis)
        require(multiplier >= 1.0)
    }

    private var currentDelayMillis = initialDelayMillis

    fun nextDelayMillis(): Long {
        val delay = currentDelayMillis
        currentDelayMillis = (currentDelayMillis * multiplier)
            .toLong()
            .coerceAtMost(maximumDelayMillis)
        return delay
    }

    fun reset() {
        currentDelayMillis = initialDelayMillis
    }
}
