import { describe, expect, it } from 'vitest'
import { Utf8StreamDecoder } from './utf8'

function encode(value: string): Uint8Array {
  return new TextEncoder().encode(value)
}

describe('Utf8StreamDecoder', () => {
  it('keeps partial Chinese and emoji code points between chunks', () => {
    const decoder = new Utf8StreamDecoder()
    const bytes = encode('A你🐈B')

    expect(decoder.decode(bytes.slice(0, 2), { stream: true })).toBe('A')
    expect(decoder.decode(bytes.slice(2, 6), { stream: true })).toBe('你')
    expect(decoder.decode(bytes.slice(6), { stream: true })).toBe('🐈B')
    expect(decoder.decode(new Uint8Array(0))).toBe('')
  })

  it('uses replacement characters for invalid or unfinished input', () => {
    const decoder = new Utf8StreamDecoder()

    expect(decoder.decode(new Uint8Array([0xff]))).toBe('\ufffd')
    expect(decoder.decode(new Uint8Array([0xe4, 0xbd]), { stream: true })).toBe('')
    expect(decoder.decode(new Uint8Array(0))).toBe('\ufffd')
  })
})
