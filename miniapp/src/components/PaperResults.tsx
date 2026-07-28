import { useState } from 'react'
import Taro from '@tarojs/taro'
import { Button, Text, View } from '@tarojs/components'
import type { PaperInfo } from '@floris/contracts'
import { translate } from '@/i18n'
import { savePaperToReading } from '@/services/papers'

export default function PaperResults({ papers }: { papers: PaperInfo[] }) {
  const [saving, setSaving] = useState('')

  const save = async (paper: PaperInfo) => {
    const id = paper.arxiv_id || paper.title
    if (saving) return
    setSaving(id)
    try {
      await savePaperToReading(paper)
      void Taro.showToast({ title: translate('addedToReading'), icon: 'success' })
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || translate('saveFailed')), icon: 'none' })
    } finally {
      setSaving('')
    }
  }

  return <View className='paper-results'>
    {papers.slice(0, 6).map((paper) => {
      const id = paper.arxiv_id || paper.title
      return <View className='paper-card' key={id}>
        <Text className='paper-title'>{paper.title}</Text>
        {paper.authors ? <Text className='paper-meta'>{paper.authors}{paper.year ? ` · ${paper.year}` : ''}</Text> : null}
        {paper.key_contribution || paper.abstract_zh
          ? <Text className='paper-summary'>{paper.key_contribution || paper.abstract_zh}</Text>
          : null}
        <View className='paper-actions'>
          <Button className='secondary-button' onClick={() => {
            const url = paper.arxiv_url || paper.source_url || paper.pdf_url || ''
            if (url) void Taro.setClipboardData({ data: url })
          }}>{translate('copySource')}</Button>
          <Button className='primary-button' loading={saving === id} onClick={() => void save(paper)}>{translate('savePaper')}</Button>
        </View>
      </View>
    })}
  </View>
}
