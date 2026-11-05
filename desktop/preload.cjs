const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('desktopPet', {
  resize: (corner, dx, dy) => ipcRenderer.send('pet:resize', { corner, dx, dy }),
  setChatMode: open => ipcRenderer.send('pet:chat-mode', open),
  setSpeechMode: open => ipcRenderer.send('pet:speech-mode', open),
})
