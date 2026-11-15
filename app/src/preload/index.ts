import { contextBridge, ipcRenderer } from 'electron'
import type { ApplyResult, ApprovedPlan, PlannedItem, ScanResult } from '../shared/types'

const api = {
  pickFolder: (): Promise<string | null> => ipcRenderer.invoke('pick-folder'),
  scan: (folder: string): Promise<ScanResult> => ipcRenderer.invoke('scan', folder),
  apply: (plan: ApprovedPlan): Promise<ApplyResult> => ipcRenderer.invoke('apply', plan),
  undo: (): Promise<ApplyResult> => ipcRenderer.invoke('undo'),
  /** Returns an error message, or null on success. */
  openFile: (relPath: string): Promise<string | null> => ipcRenderer.invoke('open-file', relPath),
  /** Returns the saved path, or null if cancelled. */
  exportIcs: (items: PlannedItem[]): Promise<string | null> => ipcRenderer.invoke('export-ics', items)
}

export type Api = typeof api

contextBridge.exposeInMainWorld('api', api)
