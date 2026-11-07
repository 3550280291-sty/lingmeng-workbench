# 灵梦工作台卸载脚本：删除快捷方式；对话记录可选择保留（自动备份到桌面）
$ErrorActionPreference = 'SilentlyContinue'
$silent = ($env:LINGMENG_SILENT -eq '1')

$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }

Write-Host ''
Write-Host '==============================================' -ForegroundColor Cyan
Write-Host '  灵梦工作台 · 卸载' -ForegroundColor Cyan
Write-Host '==============================================' -ForegroundColor Cyan
Write-Host "安装位置：$root"
Write-Host ''
$ans = 'y'
if (-not $silent) {
    $ans = Read-Host '确定要卸载吗？[y/N]'
}
if ($ans -notmatch '^[yY]') {
    Write-Host '已取消。' -ForegroundColor DarkGray
    Start-Sleep -Seconds 1
    exit 0
}

# 先停掉正在运行的实例
$lock = Join-Path $root 'data\app.lock'
if (Test-Path $lock) {
    $pidText = Get-Content $lock -Raw
    $procId = 0
    try { $procId = [int]$pidText.Trim() } catch { $procId = 0 }
    if ($procId -gt 0) {
        $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($p -and $p.MainWindowTitle -eq '灵梦工作台') { Stop-Process -Id $procId -Force }
    }
}
Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq '灵梦工作台' } | Stop-Process -Force

# 删除快捷方式
$ws = New-Object -ComObject WScript.Shell
$targets = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) '灵梦工作台.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) '灵梦工作台.lnk')
)
foreach ($lnk in $targets) {
    if (Test-Path $lnk) {
        Remove-Item $lnk -Force
        Write-Host "已删除快捷方式：$lnk"
    }
}

# 对话记录
$keepAns = 'n'
if (-not $silent) {
    $keepAns = Read-Host '要保留对话记录和上传的文件吗？[Y/n]'
}
$keepData = $keepAns -notmatch '^[nN]'
if ($keepData -and (Test-Path (Join-Path $root 'data'))) {
    $bak = Join-Path ([Environment]::GetFolderPath('Desktop')) ('灵梦工作台_数据备份_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    Move-Item (Join-Path $root 'data') $bak -Force
    Write-Host "对话记录已备份到：$bak" -ForegroundColor Yellow
}

Write-Host ''
Write-Host '正在删除程序文件...' -ForegroundColor Cyan
Start-Process -FilePath $env:ComSpec -ArgumentList '/c', ("timeout /t 3 >nul & rmdir /s /q `"$root`"") -WindowStyle Hidden
Write-Host '已卸载。' -ForegroundColor Green
Start-Sleep -Seconds 1
