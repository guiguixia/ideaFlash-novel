const { app, BrowserWindow, dialog } = require('electron')
const path = require('node:path')
const fs = require('node:fs')
const http = require('node:http')
const { spawn } = require('node:child_process')

if (require('electron-squirrel-startup')) app.quit()

const API_PORT = 8004
let backendProcess
let quitting = false

function databaseUrl(databasePath) {
  return `sqlite:///${databasePath.replaceAll('\\', '/')}`
}

function packagedResource(...parts) {
  return app.isPackaged ? path.join(process.resourcesPath, ...parts) : path.join(__dirname, '..', ...parts)
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
  backendProcess = spawn(command, args, { cwd: app.isPackaged ? undefined : path.join(__dirname, '..', 'backend'), env, stdio: 'pipe' })
  backendProcess.on('error', error => dialog.showErrorBox('本地服务无法启动', error.message))
  backendProcess.on('exit', code => {
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
    width: 1440,
    height: 920,
    minWidth: 1080,
    minHeight: 720,
    backgroundColor: '#f7f5f1',
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  })
  const devUrl = process.env.ELECTRON_START_URL
  if (devUrl) await window.loadURL(devUrl)
  else await window.loadFile(packagedResource('dist', 'index.html'))
}

app.whenReady().then(async () => {
  try {
    await createWindow()
    setupAutoUpdate()
  } catch (error) {
    dialog.showErrorBox('IdeaFlash Story 无法启动', error instanceof Error ? error.message : String(error))
    app.quit()
  }
})

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
app.on('before-quit', () => {
  quitting = true
  if (backendProcess && !backendProcess.killed) backendProcess.kill()
})
