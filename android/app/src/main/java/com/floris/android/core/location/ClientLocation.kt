package com.floris.android.core.location

import kotlinx.serialization.Serializable

/**
 * Ephemeral WGS-84 location accepted by the shared dev chat contract.
 *
 * This is transport context only. It is never persisted as profile or memory
 * data, and it expires after the same ten-minute window used by the web client.
 */
@Serializable
data class ClientLocationFix(
    val latitude: Double,
    val longitude: Double,
    val accuracyMeters: Double,
    val capturedAt: Long,
    val coordinateType: String = "wgs84",
) {
    fun isFresh(now: Long = System.currentTimeMillis()): Boolean =
        coordinateType == "wgs84" &&
            latitude.isFinite() && latitude in -90.0..90.0 &&
            longitude.isFinite() && longitude in -180.0..180.0 &&
            accuracyMeters.isFinite() && accuracyMeters in 0.0..MAX_ACCURACY_METERS &&
            capturedAt > 0 && capturedAt <= now + FUTURE_TOLERANCE_MS &&
            now - capturedAt <= MAX_AGE_MS

    companion object {
        const val MAX_AGE_MS = 10 * 60 * 1000L
        const val FUTURE_TOLERANCE_MS = 2 * 60 * 1000L
        const val MAX_ACCURACY_METERS = 5_000.0
    }
}

/** Non-sensitive outcome sent back when Maker asks the native client for GPS. */
@Serializable
data class ClientLocationRequest(
    val state: String = IDLE,
    val attemptedAt: Long = 0,
) {
    val normalizedState: String
        get() = state.takeIf { it in STATES } ?: FAILED

    companion object {
        const val AVAILABLE = "available"
        const val DENIED = "denied"
        const val TIMED_OUT = "timed_out"
        const val UNAVAILABLE = "unavailable"
        const val FAILED = "failed"
        const val IDLE = "idle"
        val STATES = setOf(AVAILABLE, DENIED, TIMED_OUT, UNAVAILABLE, FAILED, IDLE)
    }
}
