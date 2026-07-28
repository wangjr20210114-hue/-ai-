import path from 'node:path'
import { defineConfig, type UserConfigExport } from '@tarojs/cli'
import TsconfigPathsPlugin from 'tsconfig-paths-webpack-plugin'
import devConfig from './dev'
import prodConfig from './prod'

export default defineConfig<'webpack5'>(async (merge) => {
  const baseConfig: UserConfigExport<'webpack5'> = {
    projectName: 'floris-wechat-miniapp',
    date: '2026-07-28',
    designWidth: 750,
    sourceRoot: 'src',
    outputRoot: 'dist',
    framework: 'react',
    compiler: 'webpack5',
    alias: {
      '@': path.resolve(__dirname, '..', 'src'),
      '@floris/contracts': path.resolve(__dirname, '..', '..', 'packages', 'floris-contracts', 'src'),
    },
    cache: { enable: false },
    mini: {
      webpackChain(chain) {
        chain.resolve.plugin('tsconfig-paths').use(TsconfigPathsPlugin)
        chain.module
          .rule('script')
          .include
          .add(path.resolve(__dirname, '..', '..', 'packages', 'floris-contracts', 'src'))
      },
      postcss: {
        pxtransform: { enable: true, config: {} },
        cssModules: { enable: false, config: { namingPattern: 'module', generateScopedName: '[name]__[local]___[hash:base64:5]' } },
      },
    },
  }
  return merge({}, baseConfig, process.env.NODE_ENV === 'development' ? devConfig : prodConfig)
})
