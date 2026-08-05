package com.floris.android.ui.prefs

import org.junit.Assert.assertTrue
import org.junit.Test

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
}
