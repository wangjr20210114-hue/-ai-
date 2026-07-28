import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { Button, Image, View } from '@tarojs/components'
import { translate } from '@/i18n'
import { apiUrl } from '@/services/config'
import { ensureSession } from '@/services/session'

export default function MakersImage({ src, fit = false }: { src: string; fit?: boolean }) {
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
        header: {
          Authorization: `Bearer ${session.token}`,
          'x-floris-client': 'wechat-miniapp',
        },
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
      void Taro.showToast({ title: translate('savedAlbum'), icon: 'success' })
    } catch {
      const setting = await Taro.getSetting().catch(() => null)
      if (setting?.authSetting?.['scope.writePhotosAlbum'] === false) {
        const choice = await Taro.showModal({
          title: translate('albumPermissionTitle'),
          content: translate('albumPermissionBody'),
          confirmText: translate('openSettings'),
        }).catch(() => null)
        if (choice?.confirm) await Taro.openSetting().catch(() => undefined)
        return
      }
      void Taro.showToast({ title: translate('imageSaveFailed'), icon: 'none' })
    }
  }

  return <View className='makers-image-wrap'>
    <Image className={`generated-image ${fit ? 'generated-image-fit' : ''}`} mode={fit ? 'aspectFit' : 'widthFix'} src={displaySrc} showMenuByLongpress />
    <Button
      className='secondary-button save-image-button'
      disabled={loading || displaySrc.startsWith('/')}
      loading={loading}
      onClick={() => void save()}
    >
      {translate(loading ? 'loading' : 'saveAlbum')}
    </Button>
  </View>
}
