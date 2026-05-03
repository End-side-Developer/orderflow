# Run with bypass: powershell -ExecutionPolicy Bypass -File .\scripts\start-orderflow.ps1

param(
    [switch]$DryRun,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..')).Path
$WorkspaceRoot = (Resolve-Path (Join-Path $RepoRoot '..\..')).Path
$InfraDir = Join-Path $RepoRoot 'app\infra'
$BackendDir = Join-Path $RepoRoot 'app\backend'
$WorkerDir = Join-Path $RepoRoot 'app\worker'
$FrontendDir = Join-Path $RepoRoot 'app\frontend'
$LogRoot = Join-Path $RepoRoot 'tmp\startup-logs'

if (-not (Test-Path $LogRoot)) {
    New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
}

function Write-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Test-PortOpen {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Test-CommandLineLike {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Pattern
    )

    $process = Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*$Pattern*" } |
        Select-Object -First 1

    return [bool]$process
}

function Test-AllPortsOpen {
    param(
        [Parameter(Mandatory = $true)]
        [int[]]$Ports
    )

    foreach ($port in $Ports) {
        if (-not (Test-PortOpen -Port $port)) {
            return $false
        }
    }

    return $true
}

function Test-TemporalReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TemporalAddress,
        [Parameter(Mandatory = $true)]
        [string]$Namespace
    )

    if ($DryRun) {
        return $false
    }

    $pythonExe = Get-PythonExe
    $deadline = (Get-Date).AddSeconds(30)
    $probe = @"
import asyncio
from temporalio.client import Client

async def main():
    await Client.connect('$TemporalAddress', namespace='$Namespace')

asyncio.run(main())
"@

    while ((Get-Date) -lt $deadline) {
        & $pythonExe -c $probe *> $null
        if ($LASTEXITCODE -eq 0) {
            return $true
        }

        Start-Sleep -Seconds 2
    }

    return $false
}

function Wait-ForPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$ServiceName,
        [int]$TimeoutSeconds = 90
    )

    if ($DryRun) {
        return
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while (-not (Test-PortOpen -Port $Port)) {
        if ((Get-Date) -gt $deadline) {
            throw "$ServiceName did not open port $Port within $TimeoutSeconds seconds."
        }

        Start-Sleep -Seconds 1
    }
}

function Stop-LocalPortListeners {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$ServiceName
    )

    if ($DryRun) {
        Write-Host "Would stop listeners on port $Port for $ServiceName" -ForegroundColor Yellow
        return
    }

    $listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $listeners) {
        return
    }

    $processIds = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processIds) {
        if (-not $processId -or $processId -le 0) {
            continue
        }
        try {
            Stop-Process -Id $processId -Force -ErrorAction Stop
            Write-Host "$ServiceName listener stopped (PID $processId)." -ForegroundColor Yellow
        } catch {
            Write-Host "Warning: failed to stop PID $processId for ${ServiceName}: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    Start-Sleep -Seconds 1
}

function Start-LoggedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory
    )

    if ($DryRun) {
        Write-Host "Would start ${Name}: $FilePath $($ArgumentList -join ' ')" -ForegroundColor Yellow
        return
    }

    $stdoutLog = Join-Path $LogRoot "$Name.out.log"
    $stderrLog = Join-Path $LogRoot "$Name.err.log"

    if (Test-Path $stdoutLog) {
        Remove-Item $stdoutLog -Force
    }

    if (Test-Path $stderrLog) {
        Remove-Item $stderrLog -Force
    }

    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru
    Write-Host "$Name started (PID $($process.Id)). Logs: $stdoutLog | $stderrLog"
}

function Get-PythonExe {
    $candidates = @()
    $venvPython = Join-Path $WorkspaceRoot '.venv\Scripts\python.exe'

    if (Test-Path $venvPython) {
        $candidates += $venvPython
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        if ($pythonCommand.Source) {
            $candidates += $pythonCommand.Source
        } elseif ($pythonCommand.Path) {
            $candidates += $pythonCommand.Path
        }
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    throw 'Python was not found. Install Python or create the workspace .venv first.'
}

function Get-NpmExe {
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npmCommand) {
        $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
    }

    if ($npmCommand -and $npmCommand.Source) {
        return $npmCommand.Source
    }

    if ($npmCommand -and $npmCommand.Path) {
        return $npmCommand.Path
    }

    throw 'npm was not found on PATH.'
}

function Invoke-BackendMigrations {
    $pythonExe = Get-PythonExe
    Write-Step 'Running backend migrations'

    if ($DryRun) {
        Write-Host "Would run: $pythonExe -m alembic -c alembic.ini upgrade head" -ForegroundColor Yellow
        return
    }

    Push-Location $BackendDir
    try {
        & $pythonExe -m alembic -c alembic.ini upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw 'Backend migrations failed.'
        }
    } finally {
        Pop-Location
    }
}

function Ensure-Temporal {
    $temporalPort = 7233
    $temporalHost = 'localhost:7233'
    $temporalNamespace = 'default'
    $temporalContainerName = 'orderflow-temporal'
    $temporalNetwork = 'orderflow-local_default'

    if ((Test-PortOpen -Port $temporalPort) -and (Test-TemporalReady -TemporalAddress $temporalHost -Namespace $temporalNamespace)) {
        Write-Step 'Temporal already started; waiting for localhost:7233 if needed'
        Wait-ForPort -Port $temporalPort -ServiceName 'Temporal'
        return
    }

    if ($DryRun) {
        Write-Step 'Temporal not detected; would start Temporal dev server (CLI or Docker fallback)'
        return
    }

    $temporalCommand = Get-Command temporal -ErrorAction SilentlyContinue
    if ($temporalCommand) {
        Write-Step 'Starting Temporal dev server'
        Start-LoggedProcess -Name 'temporal' -FilePath $temporalCommand.Source -ArgumentList @('server', 'start-dev', '--ip', '0.0.0.0', '--port', '7233') -WorkingDirectory $RepoRoot
        Wait-ForPort -Port $temporalPort -ServiceName 'Temporal'
        return
    }

    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCommand) {
        throw 'Temporal is not running, and neither the Temporal CLI nor Docker is available.'
    }

    Write-Step 'Starting Temporal with Docker fallback'
    Push-Location $RepoRoot
    try {
        $runningContainer = & docker ps -q --filter 'name=^/orderflow-temporal$'
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to inspect the Temporal container.'
        }

        $shouldStartTemporal = $true

        if ($runningContainer) {
            Write-Host 'Temporal container already running, validating readiness.'
            if (-not (Test-TemporalReady -TemporalAddress $temporalHost -Namespace $temporalNamespace)) {
                Write-Host 'Temporal container is not ready; recreating it with the local Postgres settings.' -ForegroundColor Yellow
                & docker rm -f $temporalContainerName | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    throw 'Failed to remove the stale Temporal container.'
                }
            } else {
                $shouldStartTemporal = $false
            }
        } else {
            $existingContainer = & docker ps -a -q --filter 'name=^/orderflow-temporal$'
            if ($LASTEXITCODE -ne 0) {
                throw 'Failed to inspect existing Temporal containers.'
            }

            if ($existingContainer) {
                & docker rm -f $temporalContainerName | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    throw 'Failed to remove the stale Temporal container.'
                }
            } else {
                Write-Host 'No Temporal container found; creating a fresh one.'
            }
        }

        if ($shouldStartTemporal) {
            & docker run -d `
                --name $temporalContainerName `
                --network $temporalNetwork `
                -p 7233:7233 `
                -e DB=postgres12 `
                -e DB_PORT=5432 `
                -e DBNAME=orderflow `
                -e POSTGRES_SEEDS=orderflow-postgres `
                -e POSTGRES_USER=orderflow `
                -e POSTGRES_PWD=orderflow `
                temporalio/auto-setup:1.25 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw 'docker run for Temporal failed.'
            }
        }
    } finally {
        Pop-Location
    }

    Wait-ForPort -Port $temporalPort -ServiceName 'Temporal'
    if (-not (Test-TemporalReady -TemporalAddress $temporalHost -Namespace $temporalNamespace)) {
        throw 'Temporal port opened, but the Temporal client is not ready yet.'
    }
}

function Ensure-Infra {
    $infraPorts = @(5432, 6379, 9000, 9001, 16686, 4317, 4318)

    if (Test-AllPortsOpen -Ports $infraPorts) {
        Write-Step 'Infra already running; skipping docker compose up -d'
        return
    }

    if ($DryRun) {
        Write-Step 'Infra not fully up; would run docker compose up -d in app/infra'
        return
    }

    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCommand) {
        throw 'Docker is required for the infra stack, but Docker was not found on PATH.'
    }

    Write-Step 'Starting infra stack with Docker Compose'
    Push-Location $InfraDir
    try {
        & docker compose up -d
        if ($LASTEXITCODE -ne 0) {
            throw 'docker compose up -d failed.'
        }
    } finally {
        Pop-Location
    }

    foreach ($port in $infraPorts) {
        Wait-ForPort -Port $port -ServiceName "Infra port $port"
    }
}

function Ensure-Backend {
    $backendPort = 8000

    if (Test-PortOpen -Port $backendPort) {
        Write-Step 'Backend already started; waiting for localhost:8000 if needed'
        Wait-ForPort -Port $backendPort -ServiceName 'Backend'
        return
    }

    Invoke-BackendMigrations

    $pythonExe = Get-PythonExe
    Write-Step 'Starting backend'
    Start-LoggedProcess -Name 'backend' -FilePath $pythonExe -ArgumentList @('-m', 'uvicorn', 'orderflow_api.main:app', '--host', '0.0.0.0', '--port', '8000', '--reload') -WorkingDirectory $BackendDir
    Wait-ForPort -Port $backendPort -ServiceName 'Backend'
}

function Ensure-DemoAdvocateSeed {
    $pythonExe = Get-PythonExe
    Write-Step 'Ensuring demo advocate profiles are seeded'

    if ($DryRun) {
        Write-Host "Would run: $pythonExe -m scripts.seed_demo_advocates" -ForegroundColor Yellow
        return
    }

    Push-Location $BackendDir
    try {
        & $pythonExe -m scripts.seed_demo_advocates
        if ($LASTEXITCODE -ne 0) {
            throw 'Demo advocate seeding failed.'
        }
    } finally {
        Pop-Location
    }
}

function Test-DemoSeedLogin {
    param(
        [string]$BaseUrl = 'http://localhost:8000',
        [string]$Email = 'gov.reviewer@orderflow.example',
        [string]$Password = 'Orderflow@123'
    )

    if ($DryRun) {
        return $false
    }

    $uri = "$BaseUrl/api/v1/auth/login"
    $body = @{
        email = $Email
        password = $Password
    } | ConvertTo-Json -Compress

    try {
        $response = Invoke-RestMethod -Method Post -Uri $uri -ContentType 'application/json' -Body $body
        return [bool]($response -and $response.ok -eq $true)
    } catch {
        return $false
    }
}

function Ensure-DemoSeedLoginReady {
    if ($DryRun) {
        Write-Step 'Would verify demo seed login against backend auth endpoint'
        return
    }

    Write-Step 'Verifying demo seed login'
    if (Test-DemoSeedLogin) {
        Write-Host 'Demo seed login check passed.'
        return
    }

    Write-Host 'Demo seed login check failed; restarting backend to align runtime with seeded credentials.' -ForegroundColor Yellow
    Stop-LocalPortListeners -Port 8000 -ServiceName 'Backend'
    Ensure-Backend
    Ensure-DemoAdvocateSeed

    if (-not (Test-DemoSeedLogin)) {
        throw 'Demo seed login check still failing after backend restart. Ensure backend uses the same database as the seeder.'
    }

    Write-Host 'Demo seed login check passed after backend restart.'
}

function Ensure-Worker {
    if (Test-CommandLineLike -Pattern 'orderflow_worker.main') {
        Write-Step 'Worker already started; skipping'
        return
    }

    $pythonExe = Get-PythonExe
    Write-Step 'Starting worker'
    Start-LoggedProcess -Name 'worker' -FilePath $pythonExe -ArgumentList @('-m', 'orderflow_worker.main') -WorkingDirectory $WorkerDir
}

function Ensure-Frontend {
    $frontendPort = 3000

    if (Test-PortOpen -Port $frontendPort) {
        Write-Step 'Frontend already started; waiting for localhost:3000 if needed'
        Wait-ForPort -Port $frontendPort -ServiceName 'Frontend'
        return
    }

    $npmExe = Get-NpmExe
    Write-Step 'Starting frontend'
    Start-LoggedProcess -Name 'frontend' -FilePath $npmExe -ArgumentList @('run', 'dev') -WorkingDirectory $FrontendDir
    Wait-ForPort -Port $frontendPort -ServiceName 'Frontend'
}

Write-Step 'OrderFlow startup launcher'
Write-Host "Repo root: $RepoRoot"
Write-Host "Dry run: $DryRun"
Write-Host "Force restart: $Force"

if ($Force -and -not $DryRun) {
    Write-Step "Force stopping existing services and containers"
    $processes = Get-CimInstance Win32_Process | Where-Object {
        ($_.CommandLine -like '*uvicorn*orderflow_api.main:app*') -or
        ($_.CommandLine -like '*orderflow_worker.main*') -or
        ($_.CommandLine -like '*next-router-worker*') -or
        ($_.CommandLine -like '*next-server*') -or
        ($_.CommandLine -match 'node.*\\npm-cli\.js.*run.*dev') -or
        ($_.CommandLine -like '*temporal*server*start-dev*')
    }
    if ($processes) {
        $processes | Invoke-CimMethod -MethodName Terminate | Out-Null
    }

    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    if ($dockerCommand) {
        try { & docker rm -f orderflow-temporal 2>&1 | Out-Null } catch {}
        Push-Location $InfraDir
        try {
            & docker compose down 2>&1 | Out-Null
        } catch {
            Write-Host "Warning: docker compose down failed" -ForegroundColor Yellow
        } finally {
            Pop-Location
        }
    }
}

Ensure-Infra
Ensure-Temporal
Ensure-Backend
Ensure-DemoAdvocateSeed
Ensure-DemoSeedLoginReady
Ensure-Worker
Ensure-Frontend


Write-Host ''
Write-Host 'OrderFlow stack is ready.' -ForegroundColor Green
Write-Host 'Frontend:    http://localhost:3000'
Write-Host 'Backend:     http://localhost:8000/health'
Write-Host 'Temporal:    localhost:7233'
Write-Host "Logs:        $LogRoot"
Write-Host 'Intel layer: CLI-only; run it manually from app/intelligence when needed.'
Write-Host ''
Write-Host 'Demo seed profiles (email / password):' -ForegroundColor Yellow
Write-Host '  Government reviewer (can approve advocates):'
Write-Host '    gov.reviewer@orderflow.example / Orderflow@123'
Write-Host '  Advocate (government approved):'
Write-Host '    adv.approved@orderflow.example / Orderflow@123'
Write-Host '  Advocate (not approved yet / pending):'
Write-Host '    adv.pending@orderflow.example / Orderflow@123'
