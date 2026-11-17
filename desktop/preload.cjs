const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('desktopPet', {
  resize: (corner, dx, dy) => ipcRenderer.send('pet:resize', { corner, dx, dy }),
})
