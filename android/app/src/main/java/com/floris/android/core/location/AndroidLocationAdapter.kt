package com.floris.android.core.location

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.CancellationSignal
import android.os.Handler
import android.os.Looper
import androidx.core.content.ContextCompat
import androidx.core.location.LocationManagerCompat
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.coroutines.resume

/** Native edge adapter. Route/location decisions remain owned by the dev backend. */
object AndroidLocationAdapter {
    sealed interface Outcome {
        data class Available(val fix: ClientLocationFix) : Outcome
        data object Denied : Outcome
        data object TimedOut : Outcome
        data object Unavailable : Outcome
        data object Failed : Outcome
    }

    fun hasPermission(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    @SuppressLint("MissingPermission")
    suspend fun currentFix(
        context: Context,
        timeoutMillis: Long = 12_000,
        now: () -> Long = System::currentTimeMillis,
    ): Outcome {
        if (!hasPermission(context)) return Outcome.Denied
        val manager = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager
            ?: return Outcome.Unavailable
        val providers = listOf(
            LocationManager.NETWORK_PROVIDER,
            LocationManager.GPS_PROVIDER,
            LocationManager.PASSIVE_PROVIDER,
        ).filter { provider ->
            runCatching { provider in manager.allProviders && manager.isProviderEnabled(provider) }
                .getOrDefault(false)
        }
        if (providers.isEmpty()) return Outcome.Unavailable

        val cached = providers.mapNotNull { provider ->
            runCatching { manager.getLastKnownLocation(provider) }.getOrNull()
        }.filter { location ->
            now() - location.time <= RECENT_CACHE_MS && location.isContractSafe(now())
        }.minByOrNull { it.accuracy }
        if (cached != null) return Outcome.Available(cached.toFix())

        return suspendCancellableCoroutine { continuation ->
            val handler = Handler(Looper.getMainLooper())
            val settled = AtomicBoolean(false)
            val cancellations = mutableListOf<CancellationSignal>()
            lateinit var timeout: Runnable
            fun finish(outcome: Outcome) {
                if (!settled.compareAndSet(false, true)) return
                handler.removeCallbacks(timeout)
                cancellations.forEach(CancellationSignal::cancel)
                if (continuation.isActive) continuation.resume(outcome)
            }
            timeout = Runnable { finish(Outcome.TimedOut) }
            handler.postDelayed(timeout, timeoutMillis)
            continuation.invokeOnCancellation {
                handler.removeCallbacks(timeout)
                cancellations.forEach(CancellationSignal::cancel)
            }
            // Reuse AndroidX's API-level adapter for every enabled provider. The first
            // contract-safe fix wins; a slow network provider never blocks GPS.
            val requested = providers.map { provider ->
                val cancellation = CancellationSignal().also(cancellations::add)
                runCatching {
                    LocationManagerCompat.getCurrentLocation(
                        manager,
                        provider,
                        cancellation,
                        ContextCompat.getMainExecutor(context),
                    ) { location ->
                        if (location != null && location.isContractSafe(now())) {
                            finish(Outcome.Available(location.toFix()))
                        }
                    }
                    true
                }.getOrDefault(false)
            }.any { it }
            if (!requested) finish(Outcome.Failed)
        }
    }

    private fun Location.isContractSafe(now: Long): Boolean =
        latitude.isFinite() && latitude in -90.0..90.0 &&
            longitude.isFinite() && longitude in -180.0..180.0 &&
            accuracy.toDouble().coerceAtLeast(0.0) <= ClientLocationFix.MAX_ACCURACY_METERS &&
            time > 0 && time <= now + ClientLocationFix.FUTURE_TOLERANCE_MS &&
            now - time <= ClientLocationFix.MAX_AGE_MS

    private fun Location.toFix() = ClientLocationFix(
        latitude = latitude,
        longitude = longitude,
        accuracyMeters = accuracy.toDouble().coerceAtLeast(0.0),
        capturedAt = time,
    )

    private const val RECENT_CACHE_MS = 5 * 60 * 1000L
}
