param(
    [string]$Image = "free-bot:latest",
    [string]$Container = "free-bot",
    [switch]$Rebuild,
    [switch]$PersistDb
)

Write-Host "[free-bot] Using PowerShell to build and run Docker..." -ForegroundColor Cyan

# 1) Check Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is not installed or not on PATH. Install Docker Desktop and try again."
    exit 1
}

# 1a) Ensure Docker engine is running (Linux containers)
Write-Host "[free-bot] Checking Docker engine..." -ForegroundColor Gray
$engineReady = $false
try {
    # Try to switch to Linux desktop context if available
    $ctxList = docker context ls --format '{{.Name}}' 2>$null
    if ($LASTEXITCODE -eq 0 -and $ctxList -and ($ctxList -split "`n") -contains 'desktop-linux') {
        docker context use desktop-linux *> $null
    }
} catch {}

try {
    docker version *> $null
    if ($LASTEXITCODE -eq 0) { $engineReady = $true }
} catch {}

if (-not $engineReady) {
    Write-Warning "Docker Desktop daemon is not running or is using Windows containers."
    Write-Host "Open Docker Desktop, wait until it says 'Running', and ensure Linux containers are enabled (Settings → General → Use the WSL 2 based engine)." -ForegroundColor Yellow
    Write-Host "Then re-run: .\\Start-Docker.ps1 -Rebuild [-PersistDb]" -ForegroundColor DarkGray
    exit 1
}

# 2) Ensure .env exists
if (-not (Test-Path ".env")) {
    Write-Error ".env not found. Copy .env.example to .env and set DISCORD_TOKEN (and optionally POLL_MINUTES)."
    exit 1
}

# 3) Build image if needed
$imgExists = $true
docker image inspect $Image *> $null
if ($LASTEXITCODE -ne 0) { $imgExists = $false }

if ($Rebuild -or -not $imgExists) {
    Write-Host "[free-bot] Building image '$Image'..." -ForegroundColor Yellow
    docker build -t $Image .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "[free-bot] Using existing image '$Image'." -ForegroundColor Gray
}

# 4) Stop/remove existing container if present
$existingId = (docker ps -a --filter "name=^/$Container$" --format "{{.ID}}")
if ($existingId) {
    Write-Host "[free-bot] Stopping existing container '$Container'..." -ForegroundColor Yellow
    docker stop $Container *> $null
    docker rm $Container *> $null
}

# 5) Run new container
$args = @(
    "run","-d",
    "--name", $Container,
    "--env-file", ".env",
    "--restart","unless-stopped"
)

if ($PersistDb) {
    # Persist DB to ./data on host by mounting and pointing DB_PATH to /data/free_deals.sqlite3
    $rp = Resolve-Path ./data -ErrorAction SilentlyContinue
    if (-not $rp) {
        New-Item -ItemType Directory -Path ./data | Out-Null
        $rp = Resolve-Path ./data
    }
    $dataPath = $rp.Path  # ensure plain string path
    $args += @("-v", "${dataPath}:/data", "-e", "DB_PATH=/data/free_deals.sqlite3")
}

$args += $Image

Write-Host "[free-bot] Starting container '$Container'..." -ForegroundColor Green
& docker @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[free-bot] Running. Logs: docker logs -f $Container" -ForegroundColor Cyan
Write-Host "[free-bot] Stop/Remove: docker stop $Container; docker rm $Container" -ForegroundColor DarkGray
