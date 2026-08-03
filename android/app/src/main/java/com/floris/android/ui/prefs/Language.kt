package com.floris.android.ui.prefs

import androidx.compose.runtime.Composable
import androidx.compose.runtime.ProvidableCompositionLocal
import androidx.compose.runtime.compositionLocalOf

/** 与网页端一致的五种产品语言。 */
enum class Language(val tag: String, val label: String) {
    ZH_CN("zh-CN", "简体中文"),
    ZH_TW("zh-TW", "繁體中文"),
    EN("en", "English"),
    CAT_CUTE("cat-cute", "可爱喵喵语"),
    CAT_COLD("cat-cold", "高冷喵喵语"),
    ;

    val index: Int get() = ordinal

    companion object {
        fun fromTag(tag: String): Language = entries.firstOrNull { it.tag == tag } ?: ZH_CN
    }
}

val LocalLanguage: ProvidableCompositionLocal<Language> = compositionLocalOf { Language.ZH_CN }

/** 取当前语言下的文案。 */
@Composable
fun t(key: StringKey): String = Strings.of(key, LocalLanguage.current)

@Composable
fun t(key: StringKey, vararg args: Any): String =
    Strings.of(key, LocalLanguage.current).let { template ->
        args.foldIndexed(template) { index, acc, value -> acc.replace("{$index}", value.toString()) }
    }
