import { useMemo } from 'react'
import { RichText } from '@tarojs/components'
import { marked } from 'marked'

interface Props {
  content: string
}

export default function MarkdownMessage({ content }: Props) {
  const nodes = useMemo(
    () => marked.parse(content || '', { async: false, breaks: true }) as string,
    [content],
  )
  return <RichText className='markdown-message' nodes={nodes} userSelect />
}
