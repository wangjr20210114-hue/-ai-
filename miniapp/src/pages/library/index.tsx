import { useMemo, useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Input, Picker, ScrollView, Switch, Text, View } from '@tarojs/components'
import { openMakersDocument } from '@/services/files'
import {
  createReadingFolder,
  deleteReadingFolder,
  deleteReadingItem,
  getReadingLibrary,
  moveReadingItem,
  renameReadingFolder,
  updateReadingSetting,
  type ReadingFolder,
  type ReadingItem,
} from '@/services/library'
import { apiRequest } from '@/services/request'
import { readNativeCache, writeNativeCache } from '@/services/native-cache'
import { updateNativeTabBar } from '@/services/tabbar'
import { readLanguage, translate, type Language } from '@/i18n'
import SkeletonState from '@/components/SkeletonState'
import './index.scss'

const ALL_FOLDER = '__all__'
const UNFILED_FOLDER = '__unfiled__'
const LIBRARY_SNAPSHOT_KEY = 'floris.miniapp.screen.library.v1'

type LibrarySnapshot = {
  items: ReadingItem[]
  folders: ReadingFolder[]
  autoOrganize: boolean
}

export default function LibraryPage() {
  const [initial] = useState(() => readNativeCache<LibrarySnapshot>(LIBRARY_SNAPSHOT_KEY))
  const [items, setItems] = useState<ReadingItem[]>(initial?.items || [])
  const [folders, setFolders] = useState<ReadingFolder[]>(initial?.folders || [])
  const [autoOrganize, setAutoOrganize] = useState(initial?.autoOrganize ?? true)
  const [selectedFolder, setSelectedFolder] = useState(ALL_FOLDER)
  const [loading, setLoading] = useState(!initial)
  const [opening, setOpening] = useState('')
  const [saving, setSaving] = useState('')
  const [folderEditor, setFolderEditor] = useState<{ id: string; name: string } | null>(null)
  const [language, setLanguage] = useState<Language>(readLanguage())

  const load = async () => {
    if (!initial && !items.length && !folders.length) setLoading(true)
    try {
      const result = await getReadingLibrary()
      setItems(result.items)
      setFolders(result.folders)
      setAutoOrganize(result.settings.auto_organize)
      writeNativeCache<LibrarySnapshot>(LIBRARY_SNAPSHOT_KEY, {
        items: result.items,
        folders: result.folders,
        autoOrganize: result.settings.auto_organize,
      })
    } catch (reason) {
      void Taro.showToast({
        title: String((reason as Error)?.message || translate('readFailed')),
        icon: 'none',
      })
    } finally {
      setLoading(false)
    }
  }

  useDidShow(() => {
    const nextLanguage = readLanguage()
    setLanguage(nextLanguage)
    void Taro.setNavigationBarTitle({ title: translate('navLibrary', {}, nextLanguage) })
    void updateNativeTabBar(nextLanguage)
    void load()
  })

  const visibleItems = useMemo(() => {
    if (selectedFolder === ALL_FOLDER) return items
    if (selectedFolder === UNFILED_FOLDER) return items.filter((item) => !item.folder_id)
    return items.filter((item) => item.folder_id === selectedFolder)
  }, [items, selectedFolder])
  const activeFolder = folders.find((folder) => folder.id === selectedFolder)
  const moveOptions = [
    { id: '', name: translate('unfiledReading', {}, language) },
    ...folders.map((folder) => ({ id: folder.id, name: folder.name })),
  ]

  const open = async (item: ReadingItem) => {
    if (!item.storage_key || opening) return
    setOpening(item.id)
    try {
      await openMakersDocument(item.storage_key)
      await apiRequest('/library', {
        method: 'POST',
        data: { operation: 'touch', id: item.id },
      }).catch(() => undefined)
    } catch (reason) {
      void Taro.showToast({
        title: String((reason as Error)?.message || translate('openFailed')),
        icon: 'none',
      })
    } finally {
      setOpening('')
    }
  }

  const saveFolder = async () => {
    const name = String(folderEditor?.name || '').trim()
    if (!folderEditor || !name) return
    setSaving('folder')
    try {
      if (folderEditor.id) {
        await renameReadingFolder(folderEditor.id, name)
      } else {
        await createReadingFolder(name)
      }
      await load()
      setFolderEditor(null)
      void Taro.showToast({
        title: translate(folderEditor.id ? 'folderRenamed' : 'folderCreated', {}, language),
        icon: 'success',
      })
    } catch (reason) {
      void Taro.showToast({
        title: String((reason as Error)?.message || translate('operationFailed', {}, language)),
        icon: 'none',
      })
    } finally {
      setSaving('')
    }
  }

  const removeFolder = async () => {
    if (!activeFolder) return
    const answer = await Taro.showModal({
      title: translate('deleteFolder', {}, language),
      content: translate('deleteFolderBody', {}, language),
      confirmText: translate('delete', {}, language),
      cancelText: translate('cancel', {}, language),
      confirmColor: '#c95147',
    })
    if (!answer.confirm) return
    setSaving('folder')
    try {
      await deleteReadingFolder(activeFolder.id)
      setSelectedFolder(ALL_FOLDER)
      await load()
      void Taro.showToast({ title: translate('folderDeleted', {}, language), icon: 'success' })
    } catch (reason) {
      void Taro.showToast({
        title: String((reason as Error)?.message || translate('operationFailed', {}, language)),
        icon: 'none',
      })
    } finally {
      setSaving('')
    }
  }

  const move = async (item: ReadingItem, folderId: string) => {
    if (saving) return
    setSaving(item.id)
    try {
      await moveReadingItem(item.id, folderId)
      await load()
      void Taro.showToast({ title: translate('fileMoved', {}, language), icon: 'success' })
    } catch (reason) {
      void Taro.showToast({
        title: String((reason as Error)?.message || translate('operationFailed', {}, language)),
        icon: 'none',
      })
    } finally {
      setSaving('')
    }
  }

  const removeItem = async (item: ReadingItem) => {
    const answer = await Taro.showModal({
      title: translate('deleteReading', {}, language),
      content: translate('deleteReadingBody', {}, language),
      confirmText: translate('delete', {}, language),
      cancelText: translate('cancel', {}, language),
      confirmColor: '#c95147',
    })
    if (!answer.confirm) return
    setSaving(item.id)
    try {
      await deleteReadingItem(item.id)
      await load()
      void Taro.showToast({ title: translate('readingDeleted', {}, language), icon: 'success' })
    } catch (reason) {
      void Taro.showToast({
        title: String((reason as Error)?.message || translate('operationFailed', {}, language)),
        icon: 'none',
      })
    } finally {
      setSaving('')
    }
  }

  return <View className='library-page'>
    <View className='library-hero'>
      <Text className='library-kicker'>{translate('navLibrary', {}, language)}</Text>
      <Text className='library-title'>{translate('readingOverview', {}, language)}</Text>
      <Text className='library-count'>{items.length}</Text>
    </View>
    <View className='library-toolbar'>
      <View className='auto-organize'>
        <Text>{translate('autoOrganize', {}, language)}</Text>
        <Switch
          checked={autoOrganize}
          disabled={Boolean(saving)}
          color='#e47b3d'
          onChange={(event) => {
            const next = event.detail.value
            setAutoOrganize(next)
            setSaving('settings')
            void updateReadingSetting(next)
              .then(() => load())
              .catch(() => {
                setAutoOrganize(!next)
                void Taro.showToast({ title: translate('saveFailed', {}, language), icon: 'none' })
              })
              .finally(() => setSaving(''))
          }}
        />
      </View>
      <Button disabled={saving === 'folder'} onClick={() => setFolderEditor({ id: '', name: '' })}>
        ＋ {translate('createFolder', {}, language)}
      </Button>
    </View>

    {folderEditor ? <View className='folder-editor'>
      <Text>{translate(folderEditor.id ? 'renameFolder' : 'createFolder', {}, language)}</Text>
      <Input
        value={folderEditor.name}
        maxlength={80}
        focus
        placeholder={translate('folderNamePlaceholder', {}, language)}
        onInput={(event) => setFolderEditor({ ...folderEditor, name: event.detail.value })}
      />
      <Button disabled={Boolean(saving)} onClick={() => setFolderEditor(null)}>
        {translate('cancel', {}, language)}
      </Button>
      <Button
        className='primary'
        loading={saving === 'folder'}
        disabled={!folderEditor.name.trim() || Boolean(saving)}
        onClick={() => void saveFolder()}
      >{translate(folderEditor.id ? 'update' : 'create', {}, language)}</Button>
    </View> : null}

    <ScrollView className='folder-scroll' scrollX enableFlex>
      <View className='folder-tabs'>
        {[
          { id: ALL_FOLDER, name: translate('allReading', {}, language) },
          { id: UNFILED_FOLDER, name: translate('unfiledReading', {}, language) },
          ...folders,
        ].map((folder) => <View
          className={`folder-tab ${selectedFolder === folder.id ? 'is-active' : ''}`}
          key={folder.id}
          hoverClass='floris-press'
          hoverStayTime={80}
          onClick={() => setSelectedFolder(folder.id)}
        >{folder.name}</View>)}
      </View>
    </ScrollView>

    {activeFolder ? <View className='folder-actions'>
      <Text>{activeFolder.name}</Text>
      <Button size='mini' disabled={Boolean(saving)} onClick={() => setFolderEditor({
        id: activeFolder.id,
        name: activeFolder.name,
      })}>
        {translate('edit', {}, language)}
      </Button>
      <Button size='mini' disabled={Boolean(saving)} onClick={() => void removeFolder()}>
        {translate('delete', {}, language)}
      </Button>
    </View> : null}

    {loading ? <SkeletonState rows={5} /> : null}
    {!loading && !visibleItems.length ? <View className='library-state'>
      <Text className='library-empty-icon'>📚</Text>
      <Text>{translate('noReading', {}, language)}</Text>
      <Text>{translate('uploadReadingHint', {}, language)}</Text>
    </View> : null}
    {visibleItems.map((item) => <View className='library-item' key={item.id}>
      <View className='file-badge'>PDF</View>
      <View className='file-copy'>
        <Text className='file-title'>{item.title || item.filename || translate('pdfDocument', {}, language)}</Text>
        <Text className='file-kind'>
          {item.is_paper ? translate('paper', {}, language) : translate('pdfDocument', {}, language)}
          {' · '}{translate('nativePreview', {}, language)}
        </Text>
        <Picker
          mode='selector'
          range={moveOptions.map((option) => option.name)}
          value={Math.max(0, moveOptions.findIndex((option) => option.id === (item.folder_id || '')))}
          onChange={(event) => {
            const folderId = moveOptions[Number(event.detail.value)]?.id || ''
            if (folderId !== (item.folder_id || '')) void move(item, folderId)
          }}
        >
          <View className='move-picker'>{translate('moveToFolder', {}, language)} 〉</View>
        </Picker>
      </View>
      <View className='file-actions'>
        <Button className='assist-button' onClick={() => {
          Taro.setStorageSync('floris.miniapp.reader-file.v1', item.storage_key || '')
          void Taro.navigateTo({ url: '/pages/reader/index' })
        }}>{translate('assistReading', {}, language)}</Button>
        <Button className='open-button' loading={opening === item.id} onClick={() => void open(item)}>
          {translate('open', {}, language)}
        </Button>
        <Button className='delete-button' loading={saving === item.id} onClick={() => void removeItem(item)}>
          {translate('delete', {}, language)}
        </Button>
      </View>
    </View>)}
  </View>
}
