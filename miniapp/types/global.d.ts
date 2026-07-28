declare namespace NodeJS {
  interface ProcessEnv {
    TARO_APP_API_BASE_URL?: string
  }
}

declare module 'fast-text-encoding'

declare module '*.png' {
  const source: string
  export default source
}

declare module '*.jpg' {
  const source: string
  export default source
}
