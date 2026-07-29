type ByteInput = ArrayBuffer | ArrayBufferView

function bytesFrom(input: ByteInput): Uint8Array {
  if (input instanceof ArrayBuffer) return new Uint8Array(input)
  return new Uint8Array(input.buffer, input.byteOffset, input.byteLength)
}

function appendCodePoint(output: string[], codePoint: number): void {
  if (codePoint <= 0xffff) {
    output.push(String.fromCharCode(codePoint))
    return
  }
  const value = codePoint - 0x10000
  output.push(String.fromCharCode(
    0xd800 + (value >> 10),
    0xdc00 + (value & 0x3ff),
  ))
}

/**
 * Minimal incremental UTF-8 decoder for WeChat's chunked request transport.
 *
 * The mini-program JavaScript runtime does not consistently expose the Web
 * `TextDecoder` global. Keeping incomplete code points here also avoids a
 * polyfill silently corrupting Chinese text when a native chunk splits a
 * multi-byte character.
 */
export class Utf8StreamDecoder {
  private pending = new Uint8Array(0)

  decode(input: ByteInput, options: { stream?: boolean } = {}): string {
    const incoming = bytesFrom(input)
    const bytes = this.pending.length
      ? (() => {
          const merged = new Uint8Array(this.pending.length + incoming.length)
          merged.set(this.pending)
          merged.set(incoming, this.pending.length)
          return merged
        })()
      : incoming
    const output: string[] = []
    let index = 0

    while (index < bytes.length) {
      const first = bytes[index]
      if (first <= 0x7f) {
        output.push(String.fromCharCode(first))
        index += 1
        continue
      }

      const width = first >= 0xc2 && first <= 0xdf
        ? 2
        : first >= 0xe0 && first <= 0xef
          ? 3
          : first >= 0xf0 && first <= 0xf4
            ? 4
            : 0

      if (!width) {
        output.push('\ufffd')
        index += 1
        continue
      }

      if (index + width > bytes.length) {
        if (options.stream) break
        output.push('\ufffd')
        index = bytes.length
        continue
      }

      const second = bytes[index + 1]
      const third = width >= 3 ? bytes[index + 2] : 0
      const fourth = width === 4 ? bytes[index + 3] : 0
      const continuationValid = (
        second >= 0x80 && second <= 0xbf
        && (width < 3 || (third >= 0x80 && third <= 0xbf))
        && (width < 4 || (fourth >= 0x80 && fourth <= 0xbf))
      )
      const rangeValid = (
        (width !== 3 || first !== 0xe0 || second >= 0xa0)
        && (width !== 3 || first !== 0xed || second <= 0x9f)
        && (width !== 4 || first !== 0xf0 || second >= 0x90)
        && (width !== 4 || first !== 0xf4 || second <= 0x8f)
      )

      if (!continuationValid || !rangeValid) {
        output.push('\ufffd')
        index += 1
        continue
      }

      const codePoint = width === 2
        ? ((first & 0x1f) << 6) | (second & 0x3f)
        : width === 3
          ? ((first & 0x0f) << 12) | ((second & 0x3f) << 6) | (third & 0x3f)
          : ((first & 0x07) << 18)
            | ((second & 0x3f) << 12)
            | ((third & 0x3f) << 6)
            | (fourth & 0x3f)
      appendCodePoint(output, codePoint)
      index += width
    }

    this.pending = options.stream ? bytes.slice(index) : new Uint8Array(0)
    return output.join('')
  }
}
