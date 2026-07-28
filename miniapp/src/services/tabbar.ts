import Taro from '@tarojs/taro'
import { translate, type Language, type TranslationKey } from '@/i18n'

const labels: TranslationKey[] = [
  'tabChat',
  'tabCalendar',
  'tabReading',
  'tabProactive',
  'tabSettings',
]

export async function updateNativeTabBar(language: Language): Promise<void> {
  await Promise.all(labels.map((key, index) => (
    Taro.setTabBarItem({ index, text: translate(key, {}, language) })
  ))).catch(() => undefined)
}
