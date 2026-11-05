const { app, BrowserWindow, dialog, ipcMain } = require('electron')
const path = require('node:path')
const fs = require('node:fs')
const http = require('node:http')
const { spawn } = require('node:child_process')

const APP_NAME = '剧本刷 · ScriptRun'
const LEGACY_APP_NAME = 'IdeaFlash Story'

if (require('electron-squirrel-startup')) app.quit()

const API_PORT = 8004
let backendProcess
let backendLogFile
let quitting = false
const petOverlayState = new WeakMap()

ipcMain.on('pet:resize', (event, payload = {}) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (!win || !isPetWindowUrl(win.webContents.getURL())) return
  const corner = payload.corner
  const dx = Number(payload.dx) || 0, dy = Number(payload.dy) || 0
  const current = win.getBounds(), minWidth = 260, minHeight = 360, maxWidth = 900, maxHeight = 820
  let { x, y, width, height } = current
  if (corner.includes('e')) width = Math.max(minWidth, Math.min(maxWidth, width + dx))
  if (corner.includes('s')) height = Math.max(minHeight, Math.min(maxHeight, height + dy))
  if (corner.includes('w')) { const next = Math.max(minWidth, Math.min(maxWidth, width - dx)); x += width - next; width = next }
  if (corner.includes('n')) { const next = Math.max(minHeight, Math.min(maxHeight, height - dy)); y += height - next; height = next }
  win.setBounds({ x, y, width, height })
})

function setPetOverlayMode(win, mode, open) {
  let state = petOverlayState.get(win)
  if (!state) { state = { bounds: win.getBounds(), chat: false, speech: false }; petOverlayState.set(win, state) }
  state[mode] = open
  const current = win.getBounds(), width = state.chat ? Math.max(650, state.bounds.width) : state.speech ? Math.max(540, state.bounds.width) : state.bounds.width
  win.setBounds({ ...current, x: current.x - (width - current.width), width })
  if (!state.chat && !state.speech) petOverlayState.delete(win)
}

ipcMain.on('pet:chat-mode', (event, open) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (win && isPetWindowUrl(win.webContents.getURL())) setPetOverlayMode(win, 'chat', Boolean(open))
})

ipcMain.on('pet:speech-mode', (event, open) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (win && isPetWindowUrl(win.webContents.getURL())) setPetOverlayMode(win, 'speech', Boolean(open))
})

function databaseUrl(databasePath) {
  return `sqlite:///${databasePath.replaceAll('\\', '/')}`
}

function packagedResource(...parts) {
  return app.isPackaged ? path.join(process.resourcesPath, ...parts) : path.join(__dirname, '..', ...parts)
}

function isPetWindowUrl(rawUrl) {
  try {
    return new URL(rawUrl).pathname.endsWith('/desktop-pet/pet.html')
  } catch {
    return false
  }
}

function configurePetWindow(parent) {
  parent.webContents.setWindowOpenHandler(({ url }) => {
    if (!isPetWindowUrl(url)) return { action: 'deny' }
    return {
      action: 'allow',
      overrideBrowserWindowOptions: {
        width: 350,
        height: 520,
        minWidth: 260,
        minHeight: 360,
        frame: false,
        transparent: true,
        resizable: true,
        alwaysOnTop: true,
        skipTaskbar: true,
        hasShadow: false,
        backgroundColor: '#00000000',
        webPreferences: { contextIsolation: true, nodeIntegration: false, backgroundThrottling: false, preload: path.join(__dirname, 'preload.cjs') },
      },
    }
  })
  parent.webContents.on('did-create-window', (petWindow, details) => {
    if (!isPetWindowUrl(details.url)) return
    petWindow.setAlwaysOnTop(true, 'floating')
    petWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
    petWindow.setMenuBarVisibility(false)
  })
}

function waitForApi(timeout = 45000) {
  const startedAt = Date.now()
  return new Promise((resolve, reject) => {
    const probe = () => {
      const request = http.get(`http://127.0.0.1:${API_PORT}/health`, response => {
        response.resume()
        if (response.statusCode === 200) return resolve()
        retry()
      })
      request.on('error', retry)
      request.setTimeout(1500, () => request.destroy())
    }
    const retry = () => Date.now() - startedAt >= timeout ? reject(new Error('本地故事服务启动超时')) : setTimeout(probe, 250)
    probe()
  })
}

function startBackend() {
  if (backendProcess && !backendProcess.killed) return
  const dataDir = app.getPath('userData')
  const legacyDataDir = path.join(app.getPath('appData'), LEGACY_APP_NAME)
  if (!fs.existsSync(dataDir) && fs.existsSync(legacyDataDir)) fs.cpSync(legacyDataDir, dataDir, { recursive: true })
  fs.mkdirSync(dataDir, { recursive: true })
  const env = {
    ...process.env,
    NOVEL_API_PORT: String(API_PORT),
    NOVEL_DATABASE_URL: databaseUrl(path.join(dataDir, 'novel.db')),
    NOVEL_DATA_DIR: path.join(dataDir, 'data'),
    NO_PROXY: '127.0.0.1,localhost,::1',
    no_proxy: '127.0.0.1,localhost,::1',
  }
  const command = app.isPackaged
    ? packagedResource('bin', process.platform === 'win32' ? 'novel-server.exe' : 'novel-server')
    : (process.env.NOVEL_PYTHON_BIN || path.join(__dirname, '..', 'backend', '.venv', 'bin', 'python'))
  const args = app.isPackaged ? [] : ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(API_PORT)]
  if (!fs.existsSync(command)) throw new Error(`未找到本地故事服务：${command}`)
  const logDir = path.join(dataDir, 'logs')
  fs.mkdirSync(logDir, { recursive: true })
  backendLogFile = fs.openSync(path.join(logDir, 'sidecar.log'), 'a')
  backendProcess = spawn(command, args, { cwd: app.isPackaged ? undefined : path.join(__dirname, '..', 'backend'), env, stdio: ['ignore', backendLogFile, backendLogFile] })
  backendProcess.on('error', error => dialog.showErrorBox('本地服务无法启动', error.message))
  backendProcess.on('exit', code => {
    if (backendLogFile != null) { fs.closeSync(backendLogFile); backendLogFile = undefined }
    if (!quitting && code !== 0) dialog.showErrorBox('本地服务已停止', `服务进程异常退出（${code ?? '未知'}）`)
  })
}

function setupAutoUpdate() {
  if (!app.isPackaged) return
  const configPath = packagedResource('update-config.json')
  if (!fs.existsSync(configPath)) return
  const { baseUrl = '' } = JSON.parse(fs.readFileSync(configPath, 'utf8'))
  if (!baseUrl) return
  const { updateElectronApp, UpdateSourceType } = require('update-electron-app')
  updateElectronApp({
    updateSource: { type: UpdateSourceType.StaticStorage, baseUrl: `${baseUrl.replace(/\/$/, '')}/${process.platform}/${process.arch}` },
    logger: console,
  })
}

async function createWindow() {
  startBackend()
  await waitForApi()
  const window = new BrowserWindow({
    title: APP_NAME,
    width: 1440,
    height: 920,
    minWidth: 1080,
    minHeight: 720,
    backgroundColor: '#f7f5f1',
    webPreferences: { contextIsolation: true, nodeIntegration: false, preload: path.join(__dirname, 'preload.cjs') },
  })
  configurePetWindow(window)
  const devUrl = process.env.ELECTRON_START_URL
  if (devUrl) await window.loadURL(devUrl)
  else await window.loadFile(packagedResource('dist', 'index.html'))
}

app.whenReady().then(async () => {
  try {
    await createWindow()
    setupAutoUpdate()
  } catch (error) {
    dialog.showErrorBox(`${APP_NAME} 无法启动`, error instanceof Error ? error.message : String(error))
    app.quit()
  }
})

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
app.on('before-quit', () => {
  quitting = true
  if (backendProcess && !backendProcess.killed) backendProcess.kill()
})
