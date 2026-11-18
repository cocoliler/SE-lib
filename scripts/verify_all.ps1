[CmdletBinding()]
param(
    [string]$Python,
    [string]$Npm = "npm.cmd",
    [switch]$Bootstrap,
    [switch]$SkipBrowser,
    [switch]$SkipHttp,
    [int]$Port = 8765
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot "backend"
$frontendRoot = Join-Path $repoRoot "frontend"
$runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runRoot = Join-Path $repoRoot "evidence\runs\$runStamp"
$logsRoot = Join-Path $runRoot "logs"
$pytestTemp = Join-Path $runRoot "pytest-temp"
$runtimeRoot = Join-Path $runRoot "runtime"
$p0StateFile = Join-Path $runRoot "p0-state.json"

New-Item -ItemType Directory -Force -Path $logsRoot, $runtimeRoot | Out-Null

$steps = [System.Collections.Generic.List[object]]::new()
$script:serverProcess = $null
$overall = "PASS"
$failure = $null
$startedAt = Get-Date

$pythonCommand = $null
$npmCommand = (Get-Command $Npm -ErrorAction Stop).Source
$venvPython = Join-Path $backendRoot ".venv\Scripts\python.exe"

function Get-GitValue {
    param([string[]]$Arguments)
    $value = & git -C $repoRoot @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) {
        return ""
    }
    return ($value | Select-Object -First 1)
}

function Write-Summary {
    $finishedAt = Get-Date
    $summary = [ordered]@{
        status = $overall
        failure = $failure
        commit = Get-GitValue @("rev-parse", "HEAD")
        branch = Get-GitValue @("branch", "--show-current")
        started_at = $startedAt.ToString("o")
        finished_at = $finishedAt.ToString("o")
        mode = "TEST"
        real_executed = $false
        python = $pythonCommand
        node = (& node --version)
        npm = (& $npmCommand --version)
        steps = $steps
    }
    $summary | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath (Join-Path $runRoot "summary.json") -Encoding UTF8

    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("# Acceptance Run Summary")
    $lines.Add("")
    $lines.Add("- Status: **$overall**")
    $lines.Add("- Branch: ``$($summary.branch)``")
    $lines.Add("- Commit: ``$($summary.commit)``")
    $lines.Add("- Mode: TEST only; REAL is not executed")
    $lines.Add("- Started: $($summary.started_at)")
    $lines.Add("- Finished: $($summary.finished_at)")
    if ($failure) {
        $lines.Add("- Failure: $failure")
    }
    $lines.Add("")
    $lines.Add("| Step | Status | Seconds | Log |")
    $lines.Add("|---|---|---:|---|")
    foreach ($step in $steps) {
        $lines.Add("| $($step.name) | $($step.status) | $($step.seconds) | ``$($step.log)`` |")
    }
    $lines.Add("")
    $lines.Add("This summary records execution evidence only. Acceptance criteria remain in " +
        "``docs/testing/ACCEPTANCE_TESTS.md``.")
    $lines | Set-Content -LiteralPath (Join-Path $runRoot "summary.md") -Encoding UTF8
}

function Invoke-LoggedStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )

    $logPath = Join-Path $logsRoot "$Name.log"
    $stepStart = Get-Date
    Write-Host ""
    Write-Host "==> $Name"
    $previousErrorAction = $ErrorActionPreference
    Push-Location $WorkingDirectory
    try {
        $ErrorActionPreference = "Continue"
        $global:LASTEXITCODE = 0
        & $Command 2>&1 |
            ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) {
                    $_.Exception.Message
                }
                elseif ($_ -is [System.Management.Automation.RemoteException]) {
                    $_.Message
                }
                else {
                    $_.ToString()
                }
            } |
            Tee-Object -FilePath $logPath
        $exitCode = $LASTEXITCODE
    }
    catch {
        $_ | Out-String | Add-Content -LiteralPath $logPath -Encoding UTF8
        $steps.Add([pscustomobject]@{
            name = $Name
            status = "FAIL"
            seconds = [math]::Round(((Get-Date) - $stepStart).TotalSeconds, 3)
            exit_code = 1
            log = "logs/$Name.log"
        })
        throw
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
        Pop-Location
    }

    if ($null -eq $exitCode) {
        $exitCode = 0
    }
    $seconds = [math]::Round(((Get-Date) - $stepStart).TotalSeconds, 3)
    $status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
    $steps.Add([pscustomobject]@{
        name = $Name
        status = $status
        seconds = $seconds
        exit_code = $exitCode
        log = "logs/$Name.log"
    })
    if ($exitCode -ne 0) {
        throw "Step '$Name' failed with exit code $exitCode. See logs/$Name.log."
    }
}

function Wait-ForBackend {
    param(
        [int]$TimeoutSeconds = 30,
        [string]$LogPrefix = "server"
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($script:serverProcess.HasExited) {
            throw "Backend exited before becoming ready. See logs/$LogPrefix-stderr.log."
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 `
                -Uri "http://127.0.0.1:$Port/api/v1/projects"
            if ($response.StatusCode -eq 200) {
                return
            }
        }
        catch {
            Start-Sleep -Milliseconds 300
        }
    }
    throw "Backend did not become ready within $TimeoutSeconds seconds."
}

function Start-TestServer {
    param([string]$LogPrefix = "server")

    $env:FLOWSTUDIO_DATA_DIR = $runtimeRoot
    $env:FLOWSTUDIO_USE_ALEMBIC = "1"
    $env:FLOWSTUDIO_INSTANCE_LOCK = "1"
    $env:FLOWSTUDIO_WORKER_MODE = "thread"
    $env:FLOWSTUDIO_FRONTEND_DIST = (Join-Path $frontendRoot "dist")
    $env:FLOWSTUDIO_ALLOWED_ORIGINS = "http://127.0.0.1:$Port"

    $serverStdout = Join-Path $logsRoot "$LogPrefix-stdout.log"
    $serverStderr = Join-Path $logsRoot "$LogPrefix-stderr.log"
    $script:serverProcess = Start-Process `
        -FilePath $Python `
        -ArgumentList @("-B", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port") `
        -WorkingDirectory $backendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $serverStdout `
        -RedirectStandardError $serverStderr `
        -PassThru
    Wait-ForBackend -LogPrefix $LogPrefix
}

function Stop-TestServer {
    if ($null -ne $script:serverProcess -and -not $script:serverProcess.HasExited) {
        Stop-Process -Id $script:serverProcess.Id -Force
        Wait-Process -Id $script:serverProcess.Id -Timeout 10 -ErrorAction SilentlyContinue
    }
    $script:serverProcess = $null
}

try {
    if ($Bootstrap) {
        if (-not (Test-Path -LiteralPath $venvPython)) {
            $basePython = if ($Python) { $Python } else { (Get-Command python -ErrorAction Stop).Source }
            Invoke-LoggedStep -Name "bootstrap-venv" -WorkingDirectory $repoRoot -Command {
                & $basePython -m venv (Join-Path $backendRoot ".venv")
            }
        }
        $Python = $venvPython
        Invoke-LoggedStep -Name "bootstrap-python-deps" -WorkingDirectory $repoRoot -Command {
            & $Python -m pip install --quiet --disable-pip-version-check `
                -r (Join-Path $backendRoot "requirements.txt") `
                -r (Join-Path $backendRoot "requirements-pm.txt") `
                -r (Join-Path $repoRoot "tech\requirements.txt")
        }
        Invoke-LoggedStep -Name "bootstrap-node-deps" -WorkingDirectory $frontendRoot -Command {
            & $npmCommand ci
        }
    }

    if (-not $Python) {
        $Python = if (Test-Path -LiteralPath $venvPython) {
            $venvPython
        } else {
            (Get-Command python -ErrorAction Stop).Source
        }
    }
    $pythonCommand = $Python

    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONPATH = "$backendRoot;$repoRoot\tech"

    Invoke-LoggedStep -Name "python-preflight" -WorkingDirectory $repoRoot -Command {
        & $Python -c "import alembic, fastapi, httpx, pydantic, pytest, sqlalchemy"
    }
    Invoke-LoggedStep -Name "backend-pytest" -WorkingDirectory $repoRoot -Command {
        & $Python -B -m pytest backend/tests backend/tests_pm `
            -p no:cacheprovider -q --basetemp $pytestTemp
    }
    Invoke-LoggedStep -Name "orchestration-unittest" -WorkingDirectory $backendRoot -Command {
        & $Python -B -m unittest discover -s tests -v
    }
    Invoke-LoggedStep -Name "contract-drift" -WorkingDirectory $repoRoot -Command {
        & $Python -B tech\scripts\export_contracts.py --check
    }
    Invoke-LoggedStep -Name "openapi-drift" -WorkingDirectory $repoRoot -Command {
        & $Python -B backend\tools\export_openapi.py
    }
    Invoke-LoggedStep -Name "frontend-build" -WorkingDirectory $frontendRoot -Command {
        & $npmCommand run build
    }
    Invoke-LoggedStep -Name "frontend-domain" -WorkingDirectory $frontendRoot -Command {
        & $npmCommand test
    }

    if (-not $SkipBrowser) {
        $env:FLOWSTUDIO_SPEC_SCREENSHOT = Join-Path $runRoot "browser-spec.png"
        $env:FLOWSTUDIO_SCREENSHOT = Join-Path $runRoot "browser-workflow.png"
        $env:FLOWSTUDIO_DARK_SCREENSHOT = Join-Path $runRoot "browser-dark.png"
        Invoke-LoggedStep -Name "browser-standalone" -WorkingDirectory $frontendRoot -Command {
            & $npmCommand run test:browser
        }
    }

    if (-not $SkipHttp) {
        Start-TestServer

        if (-not $SkipBrowser) {
            $env:FLOWSTUDIO_TEST_BACKEND_URL = "http://127.0.0.1:$Port"
            Invoke-LoggedStep -Name "browser-http" -WorkingDirectory $frontendRoot -Command {
                & $npmCommand run test:browser
            }
            Remove-Item Env:FLOWSTUDIO_TEST_BACKEND_URL -ErrorAction SilentlyContinue
        }

        Invoke-LoggedStep -Name "http-e2e-test" -WorkingDirectory $backendRoot -Command {
            & $Python -B scripts\e2e_smoke.py --base-url "http://127.0.0.1:$Port"
        }
        Invoke-LoggedStep -Name "p0-http-acceptance" -WorkingDirectory $backendRoot -Command {
            & $Python -B scripts\p0_acceptance.py `
                --base-url "http://127.0.0.1:$Port" `
                --state-file $p0StateFile `
                --phase full
        }

        Stop-TestServer
        Start-TestServer -LogPrefix "server-restart"
        Invoke-LoggedStep -Name "restart-verify" -WorkingDirectory $backendRoot -Command {
            & $Python -B scripts\p0_acceptance.py `
                --base-url "http://127.0.0.1:$Port" `
                --state-file $p0StateFile `
                --phase verify
        }
    }

    Write-Host ""
    Write-Host "Acceptance baseline passed. Evidence: $runRoot"
}
catch {
    $overall = "FAIL"
    $failure = $_.Exception.Message
    Write-Host "FAILED: $failure" -ForegroundColor Red
}
finally {
    Stop-TestServer
    try {
        Write-Summary
    }
    catch {
        Write-Host "Failed to write summary: $($_.Exception.Message)" -ForegroundColor Red
    }
}

if ($overall -ne "PASS") {
    exit 1
}
