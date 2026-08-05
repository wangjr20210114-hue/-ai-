package com.floris.android.ui.prefs

import com.floris.android.core.network.ApiException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.UnknownHostException

class StringsCatalogTest {

    @Test
    fun everyVisibleKeyHasAllFiveLanguages() {
        StringKey.entries.forEach { key ->
            assertTrue("$key does not have all five languages", Strings.hasCompleteEntry(key))
            Language.entries.forEach { language ->
                val value = Strings.of(key, language)
                assertTrue("$key is blank for $language", value.isNotBlank())
            }
        }
    }

    @Test
    fun machineReadableFailuresAreLocalizedAtThePresentationBoundary() {
        val english = StringResolver { Language.EN }
        assertEquals(
            "Sign in to use this feature.",
            english.userFacingError(
                ApiException(
                    status = 403,
                    code = "LOGIN_REQUIRED",
                    requestPath = "skill_marketplace",
                ),
                StringKey.SkillsOperationFailed,
            ),
        )

        val chinese = StringResolver { Language.ZH_CN }
        assertEquals(
            "网络暂时不可用，请稍后重试",
            chinese.userFacingError(
                UnknownHostException("internal-host.example"),
                StringKey.OperationFailed,
            ),
        )
    }
}
