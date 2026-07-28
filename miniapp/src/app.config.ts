export default defineAppConfig({
  darkmode: true,
  themeLocation: 'theme.json',
  pages: [
    'pages/index/index',
    'pages/settings/index',
    'pages/history/index',
    'pages/map/index',
    'pages/library/index',
    'pages/calendar/index',
    'pages/reader/index',
    'pages/proactive/index',
  ],
  window: {
    backgroundTextStyle: '@backgroundTextStyle',
    backgroundColor: '@backgroundColor',
    backgroundColorTop: '@backgroundColor',
    backgroundColorBottom: '@backgroundColor',
    navigationBarBackgroundColor: '@navigationBarBackgroundColor',
    navigationBarTitleText: 'FLORIS',
    navigationBarTextStyle: '@navigationBarTextStyle',
  },
  tabBar: {
    color: '@tabColor',
    selectedColor: '@tabSelectedColor',
    backgroundColor: '@tabBackgroundColor',
    borderStyle: '@tabBorderStyle' as 'white',
    list: [
      { pagePath: 'pages/index/index', text: '对话', iconPath: '@chatIcon', selectedIconPath: '@chatIconActive' },
      { pagePath: 'pages/calendar/index', text: '日程', iconPath: '@calendarIcon', selectedIconPath: '@calendarIconActive' },
      { pagePath: 'pages/library/index', text: '阅读', iconPath: '@readingIcon', selectedIconPath: '@readingIconActive' },
      { pagePath: 'pages/proactive/index', text: '提醒', iconPath: '@proactiveIcon', selectedIconPath: '@proactiveIconActive' },
      { pagePath: 'pages/settings/index', text: '设置', iconPath: '@settingsIcon', selectedIconPath: '@settingsIconActive' },
    ],
  },
  permission: {
    'scope.userLocation': {
      desc: '用于附近路线与天气提醒',
    },
  },
  requiredPrivateInfos: ['getLocation'],
})
