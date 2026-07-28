import type { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'
import './app.scss'

export default function App({ children }: PropsWithChildren) {
  useLaunch(() => {
    // Authentication is initialized by the first page so failures are visible.
  })
  return children
}
