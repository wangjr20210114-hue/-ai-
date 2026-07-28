import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@tarojs/taro', () => ({
  default: {
    getStorageSync: vi.fn(() => ''),
  },
}))

import {
  supportedLanguages,
  translate,
  translationKeys,
} from './i18n'

const sourceRoot = path.resolve(process.cwd(), 'src')

function sourceFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(target)
    if (!/\.(ts|tsx)$/.test(entry.name)) return []
    if (
      entry.name === 'i18n.ts'
      || entry.name === 'app.config.ts'
      || entry.name.endsWith('.config.ts')
      || entry.name.includes('.test.')
    ) return []
    return [target]
  })
}

describe('mini-program internationalization catalog', () => {
  it('provides every fixed label in all five supported languages', () => {
    expect(supportedLanguages.map(({ id }) => id)).toEqual([
      'zh-CN',
      'zh-TW',
      'en',
      'cat-cute',
      'cat-cold',
    ])
    for (const key of translationKeys) {
      for (const { id } of supportedLanguages) {
        expect(translate(key, {}, id), `${id}.${key}`).not.toBe('')
      }
    }
  })

  it('interpolates values without changing the selected language', () => {
    expect(translate('routeSummary', { distance: '3.2', minutes: 18 }, 'en'))
      .toBe('About 3.2 km · 18 min')
    expect(translate('messageCount', { count: 7 }, 'zh-TW')).toBe('7 則')
    expect(translate('retryGeneration', {}, 'cat-cute')).toContain('喵')
  })

  it('keeps fixed user-facing Chinese copy out of components, pages, and services', () => {
    const findings = sourceFiles(sourceRoot).flatMap((file) => {
      const lines = fs.readFileSync(file, 'utf8').split('\n')
      return lines.flatMap((line, index) => (
        /[\u3400-\u9fff]/.test(line)
          ? [`${path.relative(sourceRoot, file)}:${index + 1}: ${line.trim()}`]
          : []
      ))
    })
    expect(findings).toEqual([])
  })

  it('does not depend on the web production origin at runtime', () => {
    const findings = sourceFiles(sourceRoot).flatMap((file) => (
      fs.readFileSync(file, 'utf8').includes('https://floris.jlutx.com')
        ? [path.relative(sourceRoot, file)]
        : []
    ))
    expect(findings).toEqual([])
  })
})
