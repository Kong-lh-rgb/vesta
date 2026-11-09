import { contextBridge, ipcRenderer } from 'electron'
import { closeSync, constants, fstatSync, openSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import path from 'node:path'

export type DesktopNotificationKind = 'approval' | 'run' | 'artifact'

export interface DesktopNotification {
  title: string
  body: string
  kind: DesktopNotificationKind
}

// preload 只暴露真正需要的最小 Desktop API；业务 RPC 不经过 Electron Main。
// Renderer 通过 WS /rpc 与 localhost Vesta Host 通信，媒体使用只读 HTTP transport。
const desktopApi = {
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    node: process.versions.node,
    chrome: process.versions.chrome,
  },
  getRpcToken: (): string | null => {
    let descriptor: number | null = null
    try {
      const tokenFile = path.join(homedir(), '.vesta', 'rpc-token')
      descriptor = openSync(tokenFile, constants.O_RDONLY | constants.O_NOFOLLOW)
      const info = fstatSync(descriptor)
      if (!info.isFile() || (info.mode & 0o077) !== 0) return null
      if (process.getuid && info.uid !== process.getuid()) return null
      const token = readFileSync(descriptor, 'utf8').trim()
      return /^[A-Za-z0-9_-]{32,128}$/.test(token) ? token : null
    } catch {
      return null
    } finally {
      if (descriptor !== null) closeSync(descriptor)
    }
  },
  openExternal: (url: string): Promise<boolean> =>
    ipcRenderer.invoke('vesta:open-external', url) as Promise<boolean>,
  notify: (notification: DesktopNotification): void => {
    ipcRenderer.send('vesta:notify', notification)
  },
  setApprovalVisible: (visible: boolean): void => {
    ipcRenderer.send('vesta:approval-set-visible', visible)
  },
  setApprovalSize: (height: number): void => {
    ipcRenderer.send('vesta:approval-set-size', height)
  },
} as const

contextBridge.exposeInMainWorld('vesta', desktopApi)

export type DesktopApi = typeof desktopApi
