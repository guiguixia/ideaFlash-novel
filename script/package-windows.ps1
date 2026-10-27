$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Arch = if ($env:NOVEL_DESKTOP_ARCH) { $env:NOVEL_DESKTOP_ARCH } else { 'x64' }
if ($Arch -ne 'x64' -and $Arch -ne 'arm64') {
    throw "不支持的 Windows 架构：$Arch（支持 x64 或 arm64）"
}

$Python = if ($env:NOVEL_PYTHON_BIN) { $env:NOVEL_PYTHON_BIN } else { Join-Path $Root 'backend\.venv\Scripts\python.exe' }
if (-not (Test-Path $Python)) {
    $BootstrapPython = Get-Command py -ErrorAction SilentlyContinue
    if (-not $BootstrapPython) {
        throw '未找到 Python。请安装 Python 3.11+，或设置 NOVEL_PYTHON_BIN。'
    }
    & py -3.11 -m venv (Join-Path $Root 'backend\.venv')
}

Set-Location $Root
& $Python -m pip install -r (Join-Path $Root 'backend\requirements-desktop.txt')
& $Python -m PyInstaller --noconfirm --clean --onefile --name novel-server `
    --paths (Join-Path $Root 'backend') `
    --distpath (Join-Path $Root 'desktop\bin') `
    --workpath (Join-Path $env:TEMP 'ideaflash-pyinstaller') `
    --specpath (Join-Path $env:TEMP 'ideaflash-pyinstaller-spec') `
    (Join-Path $Root 'backend\desktop_server.py')

npm run build
npx electron-forge make --platform=win32 --arch=$Arch

Write-Host "构建完成：$Root\out\make"
