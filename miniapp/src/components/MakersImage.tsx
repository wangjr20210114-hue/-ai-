import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { Button, Image, View } from '@tarojs/components'
import { apiUrl } from '@/services/config'
import { ensureSession } from '@/services/session'

export default function MakersImage({ src }: { src: string }) {
  const [displaySrc, setDisplaySrc] = useState(src)
  const [loading, setLoading] = useState(src.startsWith('/'))

  useEffect(() => {
    let disposed = false
    if (!src.startsWith('/')) {
      setDisplaySrc(src)
      setLoading(false)
      return () => { disposed = true }
    }
    setDisplaySrc(src)
    setLoading(true)
    void ensureSession()
      .then((session) => Taro.downloadFile({
        url: apiUrl(src),
        header: { Authorization: `Bearer ${session.token}` },
      }))
      .then((result) => {
        if (!disposed && result.statusCode === 200) setDisplaySrc(result.tempFilePath)
      })
      .catch(() => undefined)
      .finally(() => {
        if (!disposed) setLoading(false)
      })
    return () => { disposed = true }
  }, [src])

  const save = async () => {
    try {
      let path = displaySrc
      if (!path.startsWith('wxfile://') && !path.startsWith('http://tmp/')) {
        const result = await Taro.downloadFile({ url: path })
        path = result.tempFilePath
      }
      await Taro.saveImageToPhotosAlbum({ filePath: path })
      void Taro.showToast({ title: '已保存到相册', icon: 'success' })
    } catch {
      void Taro.showToast({ title: '未能保存，请检查相册权限', icon: 'none' })
    }
  }

  return <View className='makers-image-wrap'>
    <Image className='generated-image' mode='widthFix' src={displaySrc} showMenuByLongpress />
    <Button
      className='secondary-button save-image-button'
      disabled={loading || displaySrc.startsWith('/')}
      loading={loading}
      onClick={() => void save()}
    >
      {loading ? '正在载入' : '保存到相册'}
    </Button>
  </View>
}
