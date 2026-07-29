import { useMemo } from 'react'
import { RichText } from '@tarojs/components'
import { marked } from 'marked'
import { decorateRichTextHtml } from '@/services/markdown'

interface Props {
  content: string
}

export default function MarkdownMessage({ content }: Props) {
  const nodes = useMemo(
    () => decorateRichTextHtml(marked.parse(content || '', { async: false, breaks: true }) as string),
    [content],
  )
  return <RichText className='markdown-message' nodes={nodes} userSelect />
}
