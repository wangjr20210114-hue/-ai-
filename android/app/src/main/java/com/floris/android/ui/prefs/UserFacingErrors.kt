package com.floris.android.ui.prefs

import com.floris.android.core.network.ApiException
import retrofit2.HttpException
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

/**
 * Converts technical failures into the current UI language at the presentation
 * boundary. Domain/network code keeps stable status and error codes instead of
 * embedding text from one locale.
 */
fun StringResolver.userFacingError(error: Throwable, fallback: StringKey): String {
    val causes = generateSequence(error as Throwable?) { it.cause }.take(8).toList()
    val apiError = causes.filterIsInstance<ApiException>().firstOrNull()
    val httpError = causes.filterIsInstance<HttpException>().firstOrNull()
    val status = apiError?.status ?: httpError?.code()
    val code = apiError?.code

    val key = when {
        code == "LOGIN_REQUIRED" || status == 403 && code == null -> StringKey.LoginRequired
        code == "MEMBERSHIP_REQUIRED" -> StringKey.MembershipRequired
        status == 401 -> StringKey.SessionExpired
        status == 429 -> StringKey.TooManyRequests
        status != null && status >= 500 -> StringKey.ServiceUnavailable
        causes.any {
            it is UnknownHostException || it is ConnectException ||
                it is SocketTimeoutException || it is IOException && it !is ApiException
        } -> StringKey.NetworkUnavailable
        else -> fallback
    }
    return get(key)
}
