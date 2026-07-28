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
      desc: '用于附近路线与天气提醒 / Used for nearby routes and weather reminders',
    },
  },
  requiredPrivateInfos: ['getLocation'],
})
