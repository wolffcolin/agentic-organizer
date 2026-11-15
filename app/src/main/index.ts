import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import { writeFile } from 'fs/promises'
import { isAbsolute, join, relative, resolve } from 'path'
import { toIcs } from '../shared/ics'
import type { ApprovedPlan, PlannedItem } from '../shared/types'
import { createBackend } from './backend'

const backend = createBackend()
/** Only files under the most recently scanned folder may be opened. */
let scannedRoot: string | null = null

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    title: 'Student Folder Organizer',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })

  // Open external links in the browser, never inside the app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) shell.openExternal(url)
    return { action: 'deny' }
  })

  if (process.env.ELECTRON_RENDERER_URL) win.loadURL(process.env.ELECTRON_RENDERER_URL)
  else win.loadFile(join(__dirname, '../renderer/index.html'))
}

function registerIpc(): void {
  ipcMain.handle('pick-folder', async () => {
    const res = await dialog.showOpenDialog({ properties: ['openDirectory'] })
    return res.canceled ? null : res.filePaths[0]
  })

  ipcMain.handle('scan', async (_e, folder: string) => {
    const result = await backend.scan(folder)
    scannedRoot = folder
    return result
  })

  ipcMain.handle('apply', (_e, plan: ApprovedPlan) => backend.apply(plan))
  ipcMain.handle('undo', () => backend.undo())

  ipcMain.handle('open-file', async (_e, relPath: string) => {
    if (!scannedRoot) return 'No folder scanned yet.'
    const abs = resolve(scannedRoot, relPath)
    const rel = relative(scannedRoot, abs)
    if (rel.startsWith('..') || isAbsolute(rel)) return 'Refusing to open a file outside the scanned folder.'
    const err = await shell.openPath(abs)
    return err || null
  })

  ipcMain.handle('export-ics', async (_e, items: PlannedItem[]) => {
    const res = await dialog.showSaveDialog({
      defaultPath: 'study-plan.ics',
      filters: [{ name: 'iCalendar', extensions: ['ics'] }]
    })
    if (res.canceled || !res.filePath) return null
    await writeFile(res.filePath, toIcs(items), 'utf8')
    return res.filePath
  })
}

app.whenReady().then(() => {
  registerIpc()
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
