# Run with bypass: powershell -ExecutionPolicy Bypass -File .\scripts\start-orderflow.ps1

param(
    [switch]$DryRun
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
$IntelligenceDir = Join-Path $RepoRoot 'app\intelligence'
$DataPipelinesDir = Join-Path $RepoRoot 'app\data-pipelines'
$VenvDir = Join-Path $RepoRoot '.venv'
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
    $venvPython = Join-Path $VenvDir 'Scripts\python.exe'

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

    throw 'Python was not found. Install Python or initialize the OrderFlow root .venv first.'
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

function Invoke-CheckedCommand {
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

    Write-Step $Name
    Write-Host "Working dir: $WorkingDirectory"
    Write-Host "Command: $FilePath $($ArgumentList -join ' ')"

    if ($DryRun) {
        Write-Host "Would run command." -ForegroundColor Yellow
        return
    }

    Push-Location $WorkingDirectory
    try {
        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            throw "$Name failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
}

function Initialize-RootVenv {
    $venvPython = Join-Path $VenvDir 'Scripts\python.exe'
    if (Test-Path $venvPython) {
        Write-Step "Using existing root virtual environment"
        Write-Host $VenvDir
        return
    }

    $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        Invoke-CheckedCommand -Name 'Creating root .venv with Python 3.12' -FilePath $pythonCommand.Source -ArgumentList @('-3.12', '-m', 'venv', $VenvDir) -WorkingDirectory $RepoRoot
        return
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw 'Python was not found on PATH. Install Python 3.12 first.'
    }

    Invoke-CheckedCommand -Name 'Creating root .venv' -FilePath $pythonCommand.Source -ArgumentList @('-m', 'venv', $VenvDir) -WorkingDirectory $RepoRoot
}

function Install-PythonDependencies {
    Initialize-RootVenv
    $pythonExe = Get-PythonExe

    Invoke-CheckedCommand -Name 'Upgrading pip tooling' -FilePath $pythonExe -ArgumentList @('-m', 'pip', 'install', '--upgrade', 'pip', 'setuptools', 'wheel') -WorkingDirectory $RepoRoot
    Invoke-CheckedCommand -Name 'Installing backend Python package' -FilePath $pythonExe -ArgumentList @('-m', 'pip', 'install', '-e', '.[dev,pdf,ocr]') -WorkingDirectory $BackendDir
    Invoke-CheckedCommand -Name 'Installing worker Python package' -FilePath $pythonExe -ArgumentList @('-m', 'pip', 'install', '-e', '.[dev,ocr]') -WorkingDirectory $WorkerDir
    Invoke-CheckedCommand -Name 'Installing intelligence Python package' -FilePath $pythonExe -ArgumentList @('-m', 'pip', 'install', '-e', '.[dev]') -WorkingDirectory $IntelligenceDir
    Invoke-CheckedCommand -Name 'Installing orchestration helper dependencies' -FilePath $pythonExe -ArgumentList @('-m', 'pip', 'install', 'httpx') -WorkingDirectory $RepoRoot
    Initialize-OcrRuntime
}

function Initialize-OcrRuntime {
    Write-Step 'Verifying local OCR runtime'

    $ocrCacheDir = Join-Path $RepoRoot '.paddlex-cache'
    if (-not $env:PADDLE_PDX_CACHE_HOME) {
        $env:PADDLE_PDX_CACHE_HOME = $ocrCacheDir
    }

    Write-Host "Paddle cache: $env:PADDLE_PDX_CACHE_HOME"

    $tesseractCmd = $env:ORDERFLOW_OCR_TESSERACT_CMD
    if ([string]::IsNullOrWhiteSpace($tesseractCmd)) {
        $tesseractCmd = 'tesseract'
    }
    if (-not (Get-Command $tesseractCmd -ErrorAction SilentlyContinue)) {
        Write-Host "Tesseract fallback not found on PATH as '$tesseractCmd'. PaddleOCR will still run; install Tesseract to enable fallback OCR." -ForegroundColor Yellow
    }

    if ($DryRun) {
        Write-Host 'Would create local Paddle cache and import OCR dependencies.' -ForegroundColor Yellow
        return
    }

    if (-not (Test-Path $env:PADDLE_PDX_CACHE_HOME)) {
        New-Item -ItemType Directory -Path $env:PADDLE_PDX_CACHE_HOME -Force | Out-Null
    }

    $pythonExe = Get-PythonExe
    $probe = @"
import importlib.util

modules = ("pypdfium2", "PIL", "paddle", "paddlex", "paddleocr")
missing = [name for name in modules if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit("Missing OCR modules: " + ", ".join(missing))

from orderflow_api.api.ocr_service import extract_pdf_page_with_ocr
print("OCR runtime ready; models download on first scanned-page OCR.")
"@

    & $pythonExe -c $probe
    if ($LASTEXITCODE -ne 0) {
        throw 'OCR runtime verification failed.'
    }
}

function Install-NodeDependencies {
    $npmExe = Get-NpmExe
    Invoke-CheckedCommand -Name 'Installing frontend npm dependencies' -FilePath $npmExe -ArgumentList @('install') -WorkingDirectory $FrontendDir
}

function Ensure-EnvFiles {
    $envExampleFiles = @(
        (Join-Path $BackendDir '.env.example'),
        (Join-Path $WorkerDir '.env.example'),
        (Join-Path $IntelligenceDir '.env.example'),
        (Join-Path $FrontendDir '.env.example'),
        (Join-Path $InfraDir '.env.example'),
        (Join-Path $DataPipelinesDir '.env.example')
    )

    foreach ($examplePath in $envExampleFiles) {
        $envPath = Join-Path (Split-Path -Parent $examplePath) '.env'
        if ((Test-Path $examplePath) -and -not (Test-Path $envPath)) {
            Write-Step "Creating $envPath"
            if ($DryRun) {
                Write-Host "Would copy $examplePath to $envPath" -ForegroundColor Yellow
            } else {
                Copy-Item -LiteralPath $examplePath -Destination $envPath
            }
        }
    }
}

function Set-EnvFileValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if ($DryRun) {
        Write-Host "Would set $Key in $Path" -ForegroundColor Yellow
        return
    }

    if (-not (Test-Path $Path)) {
        New-Item -ItemType File -Path $Path -Force | Out-Null
    }

    $lines = @(Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue)
    $escapedKey = [regex]::Escape($Key)
    $matched = $false
    $updated = foreach ($line in $lines) {
        if ($line -match "^\s*$escapedKey\s*=") {
            $matched = $true
            "$Key=$Value"
        } else {
            $line
        }
    }

    if (-not $matched) {
        $updated += "$Key=$Value"
    }

    Set-Content -LiteralPath $Path -Value $updated -Encoding UTF8
}

function Get-ServiceEnvTargets {
    return @(
        @{ Name = 'backend'; Path = Join-Path $BackendDir '.env' },
        @{ Name = 'worker'; Path = Join-Path $WorkerDir '.env' },
        @{ Name = 'intelligence'; Path = Join-Path $IntelligenceDir '.env' },
        @{ Name = 'frontend'; Path = Join-Path $FrontendDir '.env' },
        @{ Name = 'infra'; Path = Join-Path $InfraDir '.env' },
        @{ Name = 'data-pipelines'; Path = Join-Path $DataPipelinesDir '.env' }
    )
}

function Get-DefaultModelForProvider {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Provider
    )

    switch ($Provider.ToLowerInvariant()) {
        'groq' { return 'llama-3.3-70b-versatile' }
        'gemini' { return 'gemini-2.0-flash' }
        'openai' { return 'gpt-4.1-mini' }
        'anthropic' { return 'claude-3-5-sonnet-latest' }
        default { return 'gemini-2.0-flash' }
    }
}

function Read-ModelSelection {
    param(
        [string]$Provider = 'gemini'
    )

    $normalizedProvider = $Provider.ToLowerInvariant()
    $presets = switch ($normalizedProvider) {
        'groq' { @('llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'gemma2-9b-it', 'mixtral-8x7b-32768') }
        'gemini' { @('gemini-2.0-flash', 'gemini-2.5-flash', 'gemini-2.5-pro') }
        'openai' { @('gpt-4.1-mini', 'gpt-4o-mini', 'gpt-4o') }
        'anthropic' { @('claude-3-5-sonnet-latest', 'claude-3-5-haiku-latest') }
        default { @(Get-DefaultModelForProvider -Provider $normalizedProvider) }
    }

    Write-Host ''
    Write-Host "Model presets for ${normalizedProvider}:"
    for ($i = 0; $i -lt $presets.Count; $i++) {
        Write-Host "  $($i + 1). $($presets[$i])"
    }
    Write-Host "  $($presets.Count + 1). Custom model name"

    $choice = Read-Host "Choose model [1]"
    if ([string]::IsNullOrWhiteSpace($choice)) {
        return $presets[0]
    }

    $choiceNumber = 0
    if ([int]::TryParse($choice, [ref]$choiceNumber)) {
        if ($choiceNumber -ge 1 -and $choiceNumber -le $presets.Count) {
            return $presets[$choiceNumber - 1]
        }
        if ($choiceNumber -eq ($presets.Count + 1)) {
            $customModel = Read-Host 'Enter custom model name'
            if (-not [string]::IsNullOrWhiteSpace($customModel)) {
                return $customModel.Trim()
            }
        }
    }

    return $choice.Trim()
}

function Configure-AIAndApiKeys {
    Ensure-EnvFiles
    Write-Step 'Configure AI, model, and API keys'
    Write-Host 'Secrets are written only to local .env files. They are not printed after entry.'
    Write-Host ''
    Write-Host 'Targets:'
    Write-Host '  1. all folders'
    Write-Host '  2. all AI services (backend, worker, intelligence)'
    Write-Host '  3. backend'
    Write-Host '  4. worker'
    Write-Host '  5. intelligence'
    Write-Host '  6. frontend'
    Write-Host '  7. infra'
    Write-Host '  8. data-pipelines'

    $targetChoice = Read-Host 'Choose target'
    $targets = switch ($targetChoice) {
        '1' { Get-ServiceEnvTargets }
        '2' { (Get-ServiceEnvTargets) | Where-Object { $_.Name -in @('backend', 'worker', 'intelligence') } }
        '3' { (Get-ServiceEnvTargets) | Where-Object { $_.Name -eq 'backend' } }
        '4' { (Get-ServiceEnvTargets) | Where-Object { $_.Name -eq 'worker' } }
        '5' { (Get-ServiceEnvTargets) | Where-Object { $_.Name -eq 'intelligence' } }
        '6' { (Get-ServiceEnvTargets) | Where-Object { $_.Name -eq 'frontend' } }
        '7' { (Get-ServiceEnvTargets) | Where-Object { $_.Name -eq 'infra' } }
        '8' { (Get-ServiceEnvTargets) | Where-Object { $_.Name -eq 'data-pipelines' } }
        default { throw 'Invalid target choice.' }
    }

    Write-Host ''
    Write-Host 'Settings:'
    Write-Host '  1. default provider and model'
    Write-Host '  2. default model only'
    Write-Host '  3. default provider only'
    Write-Host '  4. ORDERFLOW_AI_GEMINI_API_KEY'
    Write-Host '  5. ORDERFLOW_AI_GROQ_API_KEY'
    Write-Host '  6. ORDERFLOW_AI_OPENAI_API_KEY'
    Write-Host '  7. ORDERFLOW_AI_ANTHROPIC_API_KEY'
    Write-Host '  8. NEXT_PUBLIC_ORDERFLOW_API_BASE_URL'
    Write-Host '  9. Custom key'
    $keyChoice = Read-Host 'Choose setting'
    $provider = ''

    if ($keyChoice -eq '1' -or $keyChoice -eq '3') {
        $provider = Read-Host 'Default provider [gemini|groq|openai|anthropic]'
        if ([string]::IsNullOrWhiteSpace($provider)) {
            $provider = 'gemini'
        }
        $provider = $provider.Trim().ToLowerInvariant()

        foreach ($target in $targets) {
            Set-EnvFileValue -Path $target.Path -Key 'ORDERFLOW_AI_DEFAULT_PROVIDER' -Value $provider
            if ($target.Name -eq 'intelligence') {
                Set-EnvFileValue -Path $target.Path -Key 'ORDERFLOW_AI_DEFAULT_LLM_PROVIDER' -Value $provider
            }
            Write-Host "Updated provider in $($target.Name): $($target.Path)" -ForegroundColor Green
        }
    }

    if ($keyChoice -eq '1' -or $keyChoice -eq '2') {
        if ([string]::IsNullOrWhiteSpace($provider)) {
            $provider = Read-Host 'Provider for model presets [gemini|groq|openai|anthropic]'
            if ([string]::IsNullOrWhiteSpace($provider)) {
                $provider = 'gemini'
            }
            $provider = $provider.Trim().ToLowerInvariant()
        }
        $model = Read-ModelSelection -Provider $provider

        foreach ($target in $targets) {
            Set-EnvFileValue -Path $target.Path -Key 'ORDERFLOW_AI_DEFAULT_MODEL' -Value $model
            Write-Host "Updated model in $($target.Name): $($target.Path)" -ForegroundColor Green
        }
    }

    if ($keyChoice -in @('1', '2', '3')) {
        Write-Host 'Restart affected services so their config loaders pick up the new values.' -ForegroundColor Yellow
        return
    }

    $key = switch ($keyChoice) {
        '4' { 'ORDERFLOW_AI_GEMINI_API_KEY' }
        '5' { 'ORDERFLOW_AI_GROQ_API_KEY' }
        '6' { 'ORDERFLOW_AI_OPENAI_API_KEY' }
        '7' { 'ORDERFLOW_AI_ANTHROPIC_API_KEY' }
        '8' { 'NEXT_PUBLIC_ORDERFLOW_API_BASE_URL' }
        '9' { Read-Host 'Enter env/config key name' }
        default { throw 'Invalid key choice.' }
    }

    if ($key -like '*KEY*' -or $key -like '*TOKEN*' -or $key -like '*SECRET*') {
        $secureValue = Read-Host "Enter value for $key" -AsSecureString
        $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
        )
    } else {
        $value = Read-Host "Enter value for $key"
    }

    foreach ($target in $targets) {
        Set-EnvFileValue -Path $target.Path -Key $key -Value $value
        Write-Host "Updated $($target.Name): $($target.Path)" -ForegroundColor Green
    }

    Write-Host 'Restart affected services so their config loaders pick up the new values.' -ForegroundColor Yellow
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
    if ($DryRun) {
        $pythonExe = Get-PythonExe
        Write-Step 'Starting worker'
        Write-Host "Would start worker: $pythonExe -m orderflow_worker.main" -ForegroundColor Yellow
        return
    }

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

function Stop-OrderFlowStack {
    param(
        [switch]$ForceStart
    )

    if ($ForceStart -and $DryRun) {
        Write-Step "Force stopping existing services and containers"
        Write-Host 'Would stop OrderFlow processes, remove orderflow-temporal, and run docker compose down.' -ForegroundColor Yellow
        return
    }

    if ($ForceStart -and -not $DryRun) {
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
}

function Start-OrderFlowStack {
    param(
        [switch]$ForceStart
    )

    Ensure-EnvFiles
    Stop-OrderFlowStack -ForceStart:$ForceStart
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
    Write-Host 'Intel layer: CLI-only; use menu option 3 when needed.'
    Write-Host ''
    Write-Host 'Demo seed profiles (email / password):' -ForegroundColor Yellow
    Write-Host '  Government reviewer (can approve advocates):'
    Write-Host '    gov.reviewer@orderflow.example / Orderflow@123'
    Write-Host '  Advocate (government approved):'
    Write-Host '    adv.approved@orderflow.example / Orderflow@123'
    Write-Host '  Advocate (not approved yet / pending):'
    Write-Host '    adv.pending@orderflow.example / Orderflow@123'
}

function Initialize-AndStartOrderFlow {
    param(
        [switch]$ForceStart
    )

    Ensure-EnvFiles
    Install-PythonDependencies
    Install-NodeDependencies
    Start-OrderFlowStack -ForceStart:$ForceStart
}

function Invoke-OrchestrationCli {
    $pythonExe = Get-PythonExe
    $defaultPdf = Join-Path $RepoRoot 'docs\samples\court-cases\delhi-hc-wpc-8524-2025-judgment-05-02-2026.pdf'
    $defaultOutput = Join-Path $RepoRoot 'run_orchestration_output.json'

    $pdfPath = Read-Host "PDF path [$defaultPdf]"
    if ([string]::IsNullOrWhiteSpace($pdfPath)) {
        $pdfPath = $defaultPdf
    }

    $outputPath = Read-Host "Output JSON path [$defaultOutput]"
    if ([string]::IsNullOrWhiteSpace($outputPath)) {
        $outputPath = $defaultOutput
    }

    Invoke-CheckedCommand -Name 'Running CLI orchestration' -FilePath $pythonExe -ArgumentList @('run_orchestration.py', '--pdf', $pdfPath, '--output', $outputPath) -WorkingDirectory $RepoRoot

    if ((-not $DryRun) -and (Test-Path $outputPath)) {
        $result = Get-Content -Raw -LiteralPath $outputPath | ConvertFrom-Json
        Write-Host ''
        Write-Host 'Orchestration result' -ForegroundColor Green
        Write-Host "  Output:       $outputPath"
        Write-Host "  Document ID:  $($result.document_id)"
        Write-Host "  Pages:        $($result.total_pages)"
        Write-Host "  Obligations:  $($result.total_obligations_extracted)"

        if ($result.judgment_intelligence) {
            $judgment = $result.judgment_intelligence
            Write-Host "  Provider:     $($judgment._provider) / $($judgment._model)"
            Write-Host "  Recommend:    $($judgment.compliance_decision.recommendation)"
            Write-Host "  Appeal:       $($judgment.appeal_analysis.should_appeal)"
            Write-Host "  Action items: $($judgment.action_plan.items.Count)"
        }

        if ($result.judgment_intelligence_error) {
            Write-Host "  AI error:     $($result.judgment_intelligence_error)" -ForegroundColor Yellow
        }
    }
}

function Invoke-OrderFlowTests {
    $pythonExe = Get-PythonExe
    $npmExe = Get-NpmExe

    Write-Host ''
    Write-Host 'Test suites:'
    Write-Host '  1. full quality check'
    Write-Host '  2. backend tests only'
    Write-Host '  3. worker tests only'
    Write-Host '  4. intelligence tests only'
    Write-Host '  5. frontend lint/typecheck/test'
    $choice = Read-Host 'Choose test suite'

    switch ($choice) {
        '1' {
            Invoke-CheckedCommand -Name 'Running full quality check' -FilePath $pythonExe -ArgumentList @('scripts\quality_check.py') -WorkingDirectory $RepoRoot
        }
        '2' {
            Invoke-CheckedCommand -Name 'Running backend tests' -FilePath $pythonExe -ArgumentList @('-m', 'pytest', '-q') -WorkingDirectory $BackendDir
        }
        '3' {
            Invoke-CheckedCommand -Name 'Running worker tests' -FilePath $pythonExe -ArgumentList @('-m', 'pytest', '-q', 'tests') -WorkingDirectory $WorkerDir
        }
        '4' {
            Invoke-CheckedCommand -Name 'Running intelligence tests' -FilePath $pythonExe -ArgumentList @('-m', 'pytest', '-q', 'tests') -WorkingDirectory $IntelligenceDir
        }
        '5' {
            Invoke-CheckedCommand -Name 'Frontend lint' -FilePath $npmExe -ArgumentList @('run', 'lint') -WorkingDirectory $FrontendDir
            Invoke-CheckedCommand -Name 'Frontend typecheck' -FilePath $npmExe -ArgumentList @('run', 'typecheck') -WorkingDirectory $FrontendDir
            Invoke-CheckedCommand -Name 'Frontend tests' -FilePath $npmExe -ArgumentList @('run', 'test') -WorkingDirectory $FrontendDir
        }
        default {
            throw 'Invalid test suite choice.'
        }
    }
}

function Show-OrderFlowMenu {
    Write-Step 'OrderFlow launcher'
    Write-Host "Repo root: $RepoRoot"
    Write-Host "Root venv: $VenvDir"
    Write-Host "Dry run: $DryRun"
    Write-Host ''
    Write-Host '1. Start app or initialize all installs'
    Write-Host '2. Configure AI, model, and API keys (.env for all folders)'
    Write-Host '3. Run CLI orchestration'
    Write-Host '4. Run tests'
    Write-Host ''
    $choice = Read-Host 'Choose option'

    switch ($choice) {
        '1' {
            Write-Host ''
            Write-Host '1. Initialize installs, then start app'
            Write-Host '2. Start app only'
            Write-Host '3. Force start app'
            $startChoice = Read-Host 'Choose start mode'
            switch ($startChoice) {
                '1' { Initialize-AndStartOrderFlow }
                '2' { Start-OrderFlowStack }
                '3' { Start-OrderFlowStack -ForceStart }
                default { throw 'Invalid start mode.' }
            }
        }
        '2' { Configure-AIAndApiKeys }
        '3' { Invoke-OrchestrationCli }
        '4' { Invoke-OrderFlowTests }
        default { throw 'Invalid menu option.' }
    }
}

Show-OrderFlowMenu
