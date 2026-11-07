# 灵梦工作台启动器：不写死盘符，装在哪个目录都能用
$ErrorActionPreference = 'SilentlyContinue'

$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }
$data = Join-Path $root 'data'
New-Item -ItemType Directory -Force -Path $data | Out-Null
$logFile = Join-Path $data 'launch.log'

function Log([string]$msg) {
    try {
        Add-Content -Path $logFile -Value ("{0}  {1}" -f (Get-Date -Format 'HH:mm:ss'), $msg) -Encoding UTF8
    } catch { }
}

# 引入 Win32 API 辅助类，支持瞬间秒级前置激活与窗口枚举
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;

public class Win32Helper {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder strText, int maxCount);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool IsWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool BringWindowToTop(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern void SwitchToThisWindow(IntPtr hWnd, bool fAltTab);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    public static IntPtr FindLingmengWindow() {
        IntPtr result = IntPtr.Zero;
        EnumWindows(delegate(IntPtr wnd, IntPtr param) {
            if (!IsWindowVisible(wnd)) return true;
            int len = GetWindowTextLength(wnd);
            if (len > 0) {
                StringBuilder sb = new StringBuilder(len + 1);
                GetWindowText(wnd, sb, len + 1);
                string title = sb.ToString().Trim();

                // 坚决排除任何开发环境、编辑器及代码文件窗口（如 Antigravity、VS Code 等）
                if (title.IndexOf("Antigravity", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    title.IndexOf("Visual Studio", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    title.IndexOf("Cursor", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    title.Contains(".bat") || title.Contains(".ps1") || title.Contains(".py") || title.Contains(".vbs") || title.Contains(".md")) {
                    return true;
                }

                uint pid = 0;
                GetWindowThreadProcessId(wnd, out pid);
                if (pid > 0) {
                    try {
                        var proc = System.Diagnostics.Process.GetProcessById((int)pid);
                        string pname = proc.ProcessName.ToLower();
                        if (pname.Contains("antigravity") || pname.Contains("code") || pname.Contains("electron")) {
                            return true;
                        }
                    } catch { }
                }

                // 必须精确等于窗口标题，避免把 DSH/浏览器里带“灵梦工作台”字样的窗口误判成工作台
                if (title == "\u7075\u68a6\u5de5\u4f5c\u53f0" || title == "灵梦工作台") {
                    result = wnd;
                    return false;
                }
            }
            return true;
        }, IntPtr.Zero);
        return result;
    }

    public static bool ActivateHwnd(IntPtr hwnd) {
        if (hwnd == IntPtr.Zero || !IsWindow(hwnd)) return false;
        ShowWindow(hwnd, 9); // SW_RESTORE
        BringWindowToTop(hwnd);
        SetForegroundWindow(hwnd);
        try { SwitchToThisWindow(hwnd, true); } catch { }
        return true;
    }
}
"@

function Test-HttpReady([int]$port, [int]$timeoutMs = 400) {
    try {
        $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$port/api/status")
        $req.Timeout = $timeoutMs
        $req.ReadWriteTimeout = $timeoutMs
        $req.Method = "GET"
        $resp = $req.GetResponse()
        $status = [int]$resp.StatusCode
        $resp.Close()
        return ($status -ge 200 -and $status -lt 400)
    } catch {
        return $false
    }
}

function Port-Open([int]$port, [int]$timeoutMs = 300) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect('127.0.0.1', $port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($timeoutMs)) { $client.Close(); return $false }
        $client.EndConnect($iar)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

function Open-AppWindow([string]$targetUrl) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe",
        "${env:LOCALAPPDATA}\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"
    )
    $launched = $false
    foreach ($exe in $candidates) {
        if (Test-Path $exe) {
            Log "Launching standalone app window via $exe"
            Start-Process -FilePath $exe -ArgumentList @("--app=$targetUrl", "--window-size=1440,920")
            $launched = $true
            break
        }
    }
    if (-not $launched) {
        $regPaths = @(
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
            "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
        )
        foreach ($rp in $regPaths) {
            try {
                $regExe = (Get-ItemProperty -Path $rp -ErrorAction SilentlyContinue).'(default)'
                if ($regExe -and (Test-Path $regExe)) {
                    Log "Launching standalone app window via registry path: $regExe"
                    Start-Process -FilePath $regExe -ArgumentList @("--app=$targetUrl", "--window-size=1440,920")
                    $launched = $true
                    break
                }
            } catch { }
        }
    }
    if ($launched) {
        for ($s = 0; $s -lt 10; $s++) {
            Start-Sleep -Milliseconds 200
            if (Activate-LingmengWindow) { break }
        }
        return $true
    }
    Log "No Edge/Chrome found for standalone app window"
    return $false
}

function Activate-LingmengWindow {
    $hwnd = [Win32Helper]::FindLingmengWindow()
    if ($hwnd -ne [IntPtr]::Zero) {
        [Win32Helper]::ActivateHwnd($hwnd) | Out-Null
        Log "Activated existing window by Win32 enum: $hwnd"
        try { Set-Content -Path (Join-Path $data 'app.hwnd') -Value $hwnd -Encoding UTF8 -ErrorAction SilentlyContinue } catch { }
        return $true
    }
    $hwndPath = Join-Path $data 'app.hwnd'
    if (Test-Path $hwndPath) {
        try {
            $saved = [int64]((Get-Content $hwndPath -Raw).Trim())
            if ($saved -gt 0) {
                $savedHwnd = [IntPtr]$saved
                if ([Win32Helper]::IsWindow($savedHwnd)) {
                    $pidOut = [uint32]0
                    [Win32Helper]::GetWindowThreadProcessId($savedHwnd, [ref]$pidOut)
                    if ($pidOut -gt 0) {
                        $p = Get-Process -Id $pidOut -ErrorAction SilentlyContinue
                        if ($p -and $p.ProcessName -notmatch 'antigravity|code|electron') {
                            [Win32Helper]::ActivateHwnd($savedHwnd) | Out-Null
                            Log "Activated window from app.hwnd: $saved (process $($p.ProcessName))"
                            return $true
                        }
                    }
                }
            }
        } catch { }
    }
    $bp = Get-Process msedge, chrome -ErrorAction SilentlyContinue |
        Where-Object { ($_.MainWindowTitle -like '*灵梦工作台*' -or $_.MainWindowTitle -like '*\u7075\u68a6\u5de5\u4f5c\u53f0*') -and $_.MainWindowTitle -notlike '*Antigravity*' -and $_.MainWindowTitle -notlike '*.bat*' -and $_.MainWindowTitle -notlike '*.ps1*' } |
        Select-Object -First 1
    if ($bp) {
        try {
            $wsh = New-Object -ComObject WScript.Shell
            [void]$wsh.AppActivate($bp.Id)
            Log "Activated browser process window pid=$($bp.Id)"
            if ($bp.MainWindowHandle -and $bp.MainWindowHandle -ne [IntPtr]::Zero) {
                try { Set-Content -Path (Join-Path $data 'app.hwnd') -Value $bp.MainWindowHandle -Encoding UTF8 -ErrorAction SilentlyContinue } catch { }
            }
            return $true
        } catch { }
    }
    return $false
}

# 探测 Python 解释器（支持便携运行时 runtime、虚拟环境 .venv/venv、系统 PATH 中的 pythonw/python）
$pyCandidates = @(
    (Join-Path $root 'runtime\python\pythonw.exe'),
    (Join-Path $root 'runtime\python\python.exe'),
    (Join-Path $root '.venv\Scripts\pythonw.exe'),
    (Join-Path $root '.venv\Scripts\python.exe'),
    (Join-Path $root 'venv\Scripts\pythonw.exe'),
    (Join-Path $root 'venv\Scripts\python.exe')
)
$py = $null
foreach ($cand in $pyCandidates) {
    if (Test-Path $cand) {
        $py = $cand
        break
    }
}
if (-not $py) {
    $sysPy = Get-Command pythonw, python -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($sysPy) { $py = $sysPy.Source }
}

$app = Join-Path $root 'app\desktop.py'
$port = 7860

Log '---- launch ----'

if (-not $py -or -not (Test-Path $py)) {
    Log "runtime missing: neither runtime\python nor .venv/system python found"
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("未检测到 Python 运行环境：`n`n请先安装 Python 3.10+ 并运行 pip install -r requirements.txt，或解压便携运行时到 runtime 目录。", '灵梦工作台', 'OK', 'Error') | Out-Null
    return
}
Log "Using Python: $py"

$appUrl = "http://127.0.0.1:$port/?app=1"

# 1. 顶层第一道防线：检测 127.0.0.1:7860 是否已经在响应 HTTP 200
# 如果服务已经在运行，直接唤醒已有应用窗口（或调用独立应用窗口）并立即退出，绝不开多余进程
if (Test-HttpReady $port 300) {
    Log "Port $port already responding HTTP 200 at launch start."
    if (Activate-LingmengWindow) {
        Log "Existing window activated on top-level check, exiting launcher."
        return
    }
    for ($r = 0; $r -lt 8; $r++) {
        Start-Sleep -Milliseconds 150
        if (Activate-LingmengWindow) {
            Log "Existing window activated after retry on top-level check, exiting launcher."
            return
        }
    }
    Log "Service is HTTP ready, opening standalone app window on top-level check."
    Open-AppWindow $appUrl
    return
}

# 2. 全局命名互斥锁：防止极短时间内被重复狂点双击产生多重后台实例
$launcherMutexCreated = $false
$launcherMutex = $null
try {
    $launcherMutex = New-Object System.Threading.Mutex($true, "Global\LingmengWorkbenchLauncherMutex", [ref]$launcherMutexCreated)
} catch {
    $launcherMutexCreated = $true
}

if (-not $launcherMutexCreated) {
    Log "Concurrent launch detected, waiting for existing launcher or window..."
    for ($k = 0; $k -lt 50; $k++) {
        Start-Sleep -Milliseconds 200
        if (Activate-LingmengWindow) {
            Log "Window activated while waiting for peer launcher."
            if ($launcherMutex) { $launcherMutex.Close() }
            return
        }
    }
    Log "Peer launcher wait finished."
    if ($launcherMutex) { $launcherMutex.Close() }
    return
}

# 3. 获得互斥锁后二次验活：服务已经 HTTP 就绪或窗口已存在则直接唤醒并退出
if (Activate-LingmengWindow) {
    Log "Single-instance activation successful after mutex acquired, exiting launcher."
    if ($launcherMutex) { try { $launcherMutex.ReleaseMutex() } catch { }; $launcherMutex.Close() }
    return
}

if (Test-HttpReady $port 400) {
    Log "Service HTTP ready after mutex acquired."
    if (Activate-LingmengWindow) {
        if ($launcherMutex) { try { $launcherMutex.ReleaseMutex() } catch { }; $launcherMutex.Close() }
        return
    }
    for ($r = 0; $r -lt 8; $r++) {
        Start-Sleep -Milliseconds 150
        if (Activate-LingmengWindow) {
            if ($launcherMutex) { try { $launcherMutex.ReleaseMutex() } catch { }; $launcherMutex.Close() }
            return
        }
    }
    Open-AppWindow $appUrl
    if ($launcherMutex) { try { $launcherMutex.ReleaseMutex() } catch { }; $launcherMutex.Close() }
    return
}

# 4. 锁文件检测：若上一个实例还在启动中，等待就绪，严禁重复启动多个后台进程
$lock = Join-Path $data 'app.lock'
$oldPid = 0
if (Test-Path $lock) {
    try { $oldPid = [int]((Get-Content $lock -Raw).Trim()) } catch { $oldPid = 0 }
}

if ($oldPid -gt 0 -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
    Log "Live instance pid=$oldPid detected, waiting for service readiness..."
    for ($i = 0; $i -lt 80; $i++) {
        Start-Sleep -Milliseconds 200
        if (Activate-LingmengWindow) {
            if ($launcherMutex) { try { $launcherMutex.ReleaseMutex() } catch { }; $launcherMutex.Close() }
            return
        }
        if (Test-HttpReady $port 400) {
            Start-Sleep -Milliseconds 200
            if (Activate-LingmengWindow) {
                if ($launcherMutex) { try { $launcherMutex.ReleaseMutex() } catch { }; $launcherMutex.Close() }
                return
            }
            Open-AppWindow $appUrl
            if ($launcherMutex) { try { $launcherMutex.ReleaseMutex() } catch { }; $launcherMutex.Close() }
            return
        }
        if (-not (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) { break }
    }
    if (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {
        Log "Instance pid=$oldPid alive but timeout waiting for readiness, skip duplicate start."
        if ($launcherMutex) { try { $launcherMutex.ReleaseMutex() } catch { }; $launcherMutex.Close() }
        return
    }
}

# 5. 清理陈旧句柄记录，启动新后台实例并立即写入进程锁
Remove-Item (Join-Path $data 'app.hwnd') -Force -ErrorAction SilentlyContinue
Log 'Starting new python instance...'
$proc = Start-Process -FilePath $py -ArgumentList ('"' + $app + '"') -WorkingDirectory (Join-Path $root 'app') -PassThru
if ($proc -and $proc.Id) {
    Set-Content -Path $lock -Value $proc.Id -Encoding UTF8 -ErrorAction SilentlyContinue
}

# 6. 先验活再开窗：每 0.2 秒轮询请求 127.0.0.1:7860，必须确认返回 200 OK 后再开窗
$started = $false
for ($i = 0; $i -lt 150; $i++) {
    Start-Sleep -Milliseconds 200

    # 严格验证后端 HTTP 200 OK
    if (Test-HttpReady $port 400) {
        Log "Backend HTTP 200 OK confirmed in $(($i + 1) * 200)ms."
        # 等待原生 pywebview 窗口唤醒（最多等待 6 秒）
        for ($w = 0; $w -lt 30; $w++) {
            Start-Sleep -Milliseconds 200
            if (Activate-LingmengWindow) {
                $started = $true
                break
            }
            if ($proc -and $proc.HasExited) {
                break
            }
        }
        if (-not $started) {
            Log "Opening standalone browser app window (HTTP 200 verified)."
            Open-AppWindow $appUrl
            $started = $true
        }
        break
    }

    if ($proc -and $proc.HasExited -and -not (Port-Open $port 200)) {
        Log "Python process exited prematurely with code $($proc.ExitCode)"
        break
    }
}

if ($started) {
    Log "Launch completed successfully."
    if ($launcherMutex) { try { $launcherMutex.ReleaseMutex() } catch { }; $launcherMutex.Close() }
    return
}

Log 'FAILED to start'
if ($launcherMutex) { try { $launcherMutex.ReleaseMutex() } catch { }; $launcherMutex.Close() }
Add-Type -AssemblyName System.Windows.Forms
$msg = "工作台没能启动。`n`n请把下面这个目录里的日志发给我：`n$data`n（launch.log、desktop.log、desktop.out.log）`n`n常见原因：`n1. 缺少 WebView2 运行库（可先装 Edge/WebView2 再试）`n2. 内存不足（建议 8GB 以上）`n3. 杀毒软件拦截了 runtime\python\pythonw.exe"
[System.Windows.Forms.MessageBox]::Show($msg, '灵梦工作台', 'OK', 'Error') | Out-Null
