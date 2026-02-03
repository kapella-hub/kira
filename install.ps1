# Kira Installer for Windows
# Usage: irm https://raw.githubusercontent.com/kapella-hub/kira/main/install.ps1 | iex
#
# Options (set before running):
#   $env:KIRA_VERSION = "v0.2.0"  # Install specific version
#   $env:KIRA_NO_MODIFY_PATH = "1"  # Don't modify PATH

$ErrorActionPreference = "Stop"

$REPO = "https://github.com/kapella-hub/kira.git"
$VERSION = $env:KIRA_VERSION
$MIN_PYTHON_MAJOR = 3
$MIN_PYTHON_MINOR = 12

function Show-Banner {
    Write-Host ""
    Write-Host "  _    _           " -ForegroundColor Cyan
    Write-Host " | | _(_)_ __ __ _ " -ForegroundColor Cyan
    Write-Host " | |/ / | '__/ _`` |" -ForegroundColor Cyan
    Write-Host " |   <| | | | (_| |" -ForegroundColor Cyan
    Write-Host " |_|\_\_|_|  \__,_|" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Agentic CLI with memory & skills" -ForegroundColor DarkGray
    Write-Host ""
}

function Write-Info {
    param([string]$Message)
    Write-Host "==> " -ForegroundColor Blue -NoNewline
    Write-Host $Message
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[!] " -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Write-Err {
    param([string]$Message)
    Write-Host "[X] " -ForegroundColor Red -NoNewline
    Write-Host $Message
}

function Test-Python {
    Write-Info "Checking Python version..."

    # Try to find Python
    $pythonCmd = $null

    # Try py launcher first (Windows Python Launcher)
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        $pythonCmd = "py"
    }
    # Then try python
    elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
        $pythonCmd = "python"
    }
    # Then python3
    elseif (Get-Command "python3" -ErrorAction SilentlyContinue) {
        $pythonCmd = "python3"
    }

    if (-not $pythonCmd) {
        Write-Err "Python not found. Please install Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+"
        Write-Host ""
        Write-Host "Install Python from: https://www.python.org/downloads/"
        Write-Host "Make sure to check 'Add Python to PATH' during installation"
        exit 1
    }

    # Get version
    $versionOutput = & $pythonCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    $majorVersion = & $pythonCmd -c "import sys; print(sys.version_info.major)" 2>$null
    $minorVersion = & $pythonCmd -c "import sys; print(sys.version_info.minor)" 2>$null

    if ([int]$majorVersion -lt $MIN_PYTHON_MAJOR -or ([int]$majorVersion -eq $MIN_PYTHON_MAJOR -and [int]$minorVersion -lt $MIN_PYTHON_MINOR)) {
        Write-Err "Python $versionOutput found, but ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ is required"
        Write-Host ""
        Write-Host "Install Python from: https://www.python.org/downloads/"
        exit 1
    }

    $script:PythonCmd = $pythonCmd
    Write-Success "Python $versionOutput ($pythonCmd)"
}

function Test-Kiro {
    Write-Info "Checking kiro-cli..."

    if (Get-Command "kiro-cli" -ErrorAction SilentlyContinue) {
        $version = & kiro-cli --version 2>$null
        Write-Success "kiro-cli found: $version"
    }
    elseif (Get-Command "kiro" -ErrorAction SilentlyContinue) {
        $version = & kiro --version 2>$null
        Write-Success "kiro found: $version"
    }
    else {
        Write-Warn "kiro-cli not found"
        Write-Host "   kira requires kiro-cli for LLM interaction" -ForegroundColor DarkGray
        Write-Host "   Install from: https://kiro.dev" -ForegroundColor DarkGray
        Write-Host ""
    }
}

function Install-Kira {
    Write-Info "Installing kira..."

    # Build install URL with optional version
    if ($VERSION) {
        $installUrl = "git+${REPO}@${VERSION}"
        Write-Info "Installing version: $VERSION"
    } else {
        $installUrl = "git+$REPO"
    }

    # Install with pip --user
    $output = & $script:PythonCmd -m pip install --user --upgrade $installUrl 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Err "Installation failed"
        Write-Host $output
        Write-Host ""
        Write-Host "Try running manually: $script:PythonCmd -m pip install --user git+$REPO"
        exit 1
    }

    Write-Success "kira installed"
}

function Setup-Path {
    Write-Info "Setting up PATH..."

    # Get Python user scripts directory
    $scriptsPath = & $script:PythonCmd -c "import site; print(site.getusersitepackages().replace('site-packages', 'Scripts'))" 2>$null

    if (-not $scriptsPath) {
        # Fallback to common location
        $scriptsPath = "$env:APPDATA\Python\Python312\Scripts"
    }

    # Get current user PATH
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")

    if ($userPath -like "*$scriptsPath*") {
        Write-Success "PATH already configured"
        return
    }

    # Add to user PATH
    $newPath = "$scriptsPath;$userPath"
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")

    # Update current session
    $env:PATH = "$scriptsPath;$env:PATH"

    Write-Success "Added $scriptsPath to PATH"
}

function Test-Installation {
    Write-Info "Verifying installation..."

    # Refresh PATH for current session
    $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine")

    if (Get-Command "kira" -ErrorAction SilentlyContinue) {
        $version = & kira version 2>$null | Select-Object -First 1
        Write-Success "kira is ready: $version"
    }
    else {
        # Try with Python module
        $version = & $script:PythonCmd -m kira version 2>$null | Select-Object -First 1
        if ($version) {
            Write-Success "kira is ready: $version"
            Write-Warn "Restart your terminal to use 'kira' command directly"
        }
        else {
            Write-Err "Installation verification failed"
            Write-Host "Try running: $script:PythonCmd -m pip install --user git+$REPO"
            exit 1
        }
    }
}

function Show-Success {
    Write-Host ""
    Write-Host "Installation complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Get started:"
    Write-Host "  kira              " -ForegroundColor Cyan -NoNewline
    Write-Host "Start interactive REPL"
    Write-Host "  kira chat `"...`"   " -ForegroundColor Cyan -NoNewline
    Write-Host "One-shot prompt"
    Write-Host "  kira --help       " -ForegroundColor Cyan -NoNewline
    Write-Host "Show all commands"
    Write-Host ""
    Write-Host "Update:"
    Write-Host "  kira update       " -ForegroundColor Cyan -NoNewline
    Write-Host "Update to latest version"
    Write-Host ""
    Write-Host "Note: You may need to restart your terminal for PATH changes to take effect." -ForegroundColor DarkGray
    Write-Host ""
}

function Main {
    Show-Banner
    Test-Python
    Test-Kiro
    Install-Kira
    Setup-Path
    Test-Installation
    Show-Success
}

Main
