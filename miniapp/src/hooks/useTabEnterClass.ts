import { useState } from 'react'
import { useDidShow } from '@tarojs/taro'

/**
 * Native tab switches cannot animate, so each tab page replays a subtle
 * rise-and-fade on every show. Toggling between two identical animation
 * names restarts the CSS animation without remounting (scroll positions
 * and component state stay intact).
 */
export function useTabEnterClass(): string {
  const [flip, setFlip] = useState(false)
  useDidShow(() => setFlip((value) => !value))
  return `floris-page-enter ${flip ? 'is-run-a' : 'is-run-b'}`
}
