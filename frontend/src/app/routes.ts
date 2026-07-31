export type AppRoute = 'chat' | 'skills';

export function routeFromPath(pathname: string): AppRoute {
  return pathname.includes('skill') ? 'skills' : 'chat';
}

export const APP_PATHS = Object.freeze({
  chat: '/chatBot/',
  skills: '/skill_marketplace',
});
