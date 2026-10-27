const path = require('node:path')

const updateBaseUrl = (process.env.NOVEL_UPDATE_BASE_URL || '').replace(/\/$/, '')

module.exports = {
  packagerConfig: {
    asar: true,
    icon: path.join(__dirname, 'desktop', 'icon'),
    extraResource: [
      'web/dist',
      'desktop/bin',
      'desktop/update-config.json',
    ],
  },
  makers: [
    { name: '@electron-forge/maker-dmg', platforms: ['darwin'] },
    {
      name: '@electron-forge/maker-zip',
      platforms: ['darwin'],
      config: arch => updateBaseUrl ? { macUpdateManifestBaseUrl: `${updateBaseUrl}/darwin/${arch}` } : {},
    },
    {
      name: '@electron-forge/maker-squirrel',
      platforms: ['win32'],
      config: arch => updateBaseUrl ? { remoteReleases: `${updateBaseUrl}/win32/${arch}` } : {},
    },
  ],
}
