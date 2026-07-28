export default defineAppConfig({
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
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#fff7ed',
    navigationBarTitleText: 'FLORIS',
    navigationBarTextStyle: 'black',
  },
  tabBar: {
    color: '#8f6a55',
    selectedColor: '#df7132',
    backgroundColor: '#fffaf4',
    borderStyle: 'white',
    list: [
      { pagePath: 'pages/index/index', text: '对话' },
      { pagePath: 'pages/calendar/index', text: '日程' },
      { pagePath: 'pages/library/index', text: '阅读' },
      { pagePath: 'pages/proactive/index', text: '提醒' },
      { pagePath: 'pages/settings/index', text: '设置' },
    ],
  },
  permission: {
    'scope.userLocation': {
      desc: '用于附近路线与天气提醒',
    },
  },
  requiredPrivateInfos: ['getLocation'],
})
