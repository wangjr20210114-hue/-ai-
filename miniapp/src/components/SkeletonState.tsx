import { View } from '@tarojs/components'

/** Shared shimmer placeholder shown while a page fetches its first data. */
export default function SkeletonState({ rows = 3 }: { rows?: number }) {
  return (
    <View className='skeleton-state'>
      {Array.from({ length: rows }).map((_, index) => (
        <View key={index} className={`skeleton-state-bar skeleton-state-bar-${(index % 3) + 1}`} />
      ))}
    </View>
  )
}
