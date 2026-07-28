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
  permission: {
    'scope.userLocation': {
      desc: '用于按当前位置规划路线和提供天气相关提醒',
    },
  },
  requiredPrivateInfos: ['getLocation'],
})
