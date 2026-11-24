<#
.SYNOPSIS
    Build reprodutível do instalador Windows do Registrale-DOU (`Registrale-Setup-<versão>.exe`).

.DESCRIPTION
    1. Baixa o Python 3.11 embeddable (versão fixa com verificação SHA-256).
    2. Exporta dependências travadas do `uv.lock` (grupo `windows`) e instala em `site-packages/`.
    3. Copia a aplicação (`rodou_dashboard/`, `src/`, `compat/`, `dag_confs/`, `windows/`) e o PostgreSQL 17 portátil.
    4. Gera `dist/Registrale-Setup-<versão>.exe` via Inno Setup e grava o arquivo `.sha256`.
#>

[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$PythonVersion = "3.11.9",
    [string]$PythonSha256 = "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b",
    [string]$PostgresUrl = "https://get.enterprisedb.com/postgresql/postgresql-17.2-1-windows-x64-binaries.zip",
    [string]$PostgresSha256 = "",
    [switch]$SkipPostgresDownload,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $RepoRoot "build"
$CacheDir = Join-Path $BuildRoot "cache"
$StageDir = Join-Path $BuildRoot "stage"
$DistDir = Join-Path $RepoRoot "dist"

if (-not $Version) {
    $VersionFile = Join-Path $RepoRoot "VERSION"
    if (Test-Path $VersionFile) {
        $Version = (Get-Content $VersionFile -Raw).Trim().TrimStart("v", "V")
    } else {
        $PyProject = Get-Content (Join-Path $RepoRoot "pyproject.toml") -Raw
        if ($PyProject -match '(?m)^version\s*=\s*"([^"]+)"') {
            $Version = $Matches[1].Trim()
        } else {
            $Version = "0.1.0"
        }
    }
}

Write-Host "==> Registrale-DOU Build v$Version" -ForegroundColor Cyan

# Verifica se windows/registrale.ico existe e está atualizado em relação a rodou_dashboard/static/icon.svg
$IconSvg = Join-Path $RepoRoot "rodou_dashboard\static\icon.svg"
$IconIco = Join-Path $PSScriptRoot "registrale.ico"
if (-not (Test-Path $IconIco)) {
    throw "Ícone '$IconIco' não encontrado. Execute 'uv run python windows/make_icon.py' antes do build."
}
if ((Test-Path $IconSvg) -and ((Get-Item $IconSvg).LastWriteTimeUtc -gt (Get-Item $IconIco).LastWriteTimeUtc)) {
    throw "O ícone '$IconIco' está mais antigo que '$IconSvg'. Execute 'uv run python windows/make_icon.py' para atualizá-lo."
}

New-Item -ItemType Directory -Force -Path $CacheDir, $DistDir | Out-Null
if (Test-Path $StageDir) {
    Remove-Item -Recurse -Force $StageDir
}
$PythonStage = Join-Path $StageDir "python"
$SitePackagesStage = Join-Path $StageDir "site-packages"
$AppStage = Join-Path $StageDir "app"
New-Item -ItemType Directory -Force -Path $PythonStage, $SitePackagesStage, $AppStage | Out-Null

function Assert-FileSha256 {
    param([string]$Path, [string]$ExpectedHash)
    $Actual = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
    $Expected = $ExpectedHash.Trim().ToLowerInvariant()
    if ($Actual -ne $Expected) {
        throw "Falha na verificação SHA-256 de '$Path'. Esperado: $Expected | Obtido: $Actual"
    }
    Write-Host "    SHA-256 verificado: $Actual" -ForegroundColor Green
}

# 1. Python 3.11 embeddable
$PythonZipName = "python-$PythonVersion-embed-amd64.zip"
$PythonZipUrl = "https://www.python.org/ftp/python/$PythonVersion/$PythonZipName"
$PythonZipPath = Join-Path $CacheDir $PythonZipName

if (-not (Test-Path $PythonZipPath)) {
    Write-Host "==> Baixando Python $PythonVersion embeddable..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $PythonZipUrl -OutFile $PythonZipPath -UseBasicParsing
}
Assert-FileSha256 -Path $PythonZipPath -ExpectedHash $PythonSha256

Write-Host "==> Extraindo Python embeddable..." -ForegroundColor Cyan
Expand-Archive -Path $PythonZipPath -DestinationPath $PythonStage -Force

# Ajusta python311._pth para habilitar site-packages e app
$PthFile = Get-ChildItem -Path $PythonStage -Filter "python*._pth" | Select-Object -First 1
if (-not $PthFile) {
    throw "Arquivo python*._pth não encontrado em $PythonStage"
}
$PthLines = @(
    "python311.zip",
    ".",
    "..\app",
    "..\site-packages",
    "import site"
)
Set-Content -Path $PthFile.FullName -Value $PthLines -Encoding ASCII

# 2. Exporta e instala dependências travadas
$ReqFile = Join-Path $BuildRoot "requirements-windows.txt"
Write-Host "==> Exportando dependências travadas via uv..." -ForegroundColor Cyan
Push-Location $RepoRoot
try {
    & uv export --frozen --no-dev --no-emit-project --group windows --no-hashes -o $ReqFile
    if ($LASTEXITCODE -ne 0) { throw "Falha ao executar uv export" }

    Write-Host "==> Instalando dependências em site-packages..." -ForegroundColor Cyan
    & uv pip install --python-version $PythonVersion --target $SitePackagesStage -r $ReqFile
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar dependências em $SitePackagesStage" }
}
finally {
    Pop-Location
}

# 3. Copia aplicação
Write-Host "==> Copiando código da aplicação..." -ForegroundColor Cyan
$DirsToCopy = @("rodou_dashboard", "src", "compat", "dag_confs")
foreach ($Dir in $DirsToCopy) {
    $SrcPath = Join-Path $RepoRoot $Dir
    if (Test-Path $SrcPath) {
        Copy-Item -Path $SrcPath -Destination (Join-Path $AppStage $Dir) -Recurse -Force
    }
}

# Remove pastas de testes, caches e artefatos locais do pacote final
Get-ChildItem -Path $AppStage -Include "__pycache__",".pytest_cache","tests" -Directory -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Copy-Item -Path (Join-Path $RepoRoot "pyproject.toml") -Destination $AppStage -Force
Set-Content -Path (Join-Path $AppStage "VERSION") -Value $Version -Encoding UTF8
$WinStage = Join-Path $AppStage "windows"
New-Item -ItemType Directory -Force -Path $WinStage | Out-Null
Copy-Item -Path (Join-Path $PSScriptRoot "launcher.pyw") -Destination $WinStage -Force
Copy-Item -Path (Join-Path $PSScriptRoot "registrale.ico") -Destination $WinStage -Force

# 4. PostgreSQL portátil (usa windows/vendor/pgsql se existir ou baixa binários oficiais)
$VendorPgDst = Join-Path $WinStage "vendor\pgsql"
$LocalVendorPg = Join-Path $PSScriptRoot "vendor\pgsql"

if (Test-Path (Join-Path $LocalVendorPg "bin\pg_ctl.exe")) {
    Write-Host "==> Copiando PostgreSQL portátil local de windows/vendor/pgsql..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $VendorPgDst | Out-Null
    foreach ($Sub in @("bin", "lib", "share")) {
        $SubPath = Join-Path $LocalVendorPg $Sub
        if (Test-Path $SubPath) {
            Copy-Item -Path $SubPath -Destination (Join-Path $VendorPgDst $Sub) -Recurse -Force
        }
    }
} elseif (-not $SkipPostgresDownload) {
    if (-not $PostgresSha256) {
        throw "Forneça -PostgresSha256 para validar a integridade do download do PostgreSQL portátil (ou use -SkipPostgresDownload / windows\vendor\pgsql)."
    }
    $PgZipPath = Join-Path $CacheDir "postgresql-windows-x64-binaries.zip"
    if (-not (Test-Path $PgZipPath)) {
        Write-Host "==> Baixando binários portáteis do PostgreSQL 17..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $PostgresUrl -OutFile $PgZipPath -UseBasicParsing
    }
    Assert-FileSha256 -Path $PgZipPath -ExpectedHash $PostgresSha256
    $PgExtractTmp = Join-Path $BuildRoot "pg_extract"
    if (Test-Path $PgExtractTmp) { Remove-Item -Recurse -Force $PgExtractTmp }
    Expand-Archive -Path $PgZipPath -DestinationPath $PgExtractTmp -Force
    $PgExtractedRoot = Join-Path $PgExtractTmp "pgsql"
    if (-not (Test-Path (Join-Path $PgExtractedRoot "bin\pg_ctl.exe"))) {
        throw "Estrutura inesperada no ZIP do PostgreSQL portátil."
    }
    New-Item -ItemType Directory -Force -Path $VendorPgDst | Out-Null
    foreach ($Sub in @("bin", "lib", "share")) {
        Copy-Item -Path (Join-Path $PgExtractedRoot $Sub) -Destination (Join-Path $VendorPgDst $Sub) -Recurse -Force
    }
    Remove-Item -Recurse -Force $PgExtractTmp
} else {
    Write-Warning "PostgreSQL portátil não incluído (-SkipPostgresDownload)."
}

if ($SkipInstaller) {
    Write-Host "==> Build de staging concluído em $StageDir (-SkipInstaller ativo)." -ForegroundColor Green
    exit 0
}

# 5. Compila instalador com Inno Setup
$IsccCandidates = @(
    (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) }

$IsccExe = $IsccCandidates | Select-Object -First 1
if (-not $IsccExe) {
    throw "Inno Setup 6 (ISCC.exe) não encontrado. Instale Inno Setup 6 ou execute com -SkipInstaller."
}

$IssPath = Join-Path $PSScriptRoot "installer.iss"
Write-Host "==> Compilando instalador com Inno Setup ($IsccExe)..." -ForegroundColor Cyan
& $IsccExe "/DAppVersion=$Version" "/DStageDir=$StageDir" "/DOutputDir=$DistDir" $IssPath
if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar installer.iss" }

$SetupExe = Join-Path $DistDir "Registrale-Setup-$Version.exe"
if (-not (Test-Path $SetupExe)) {
    throw "Instalador esperado não encontrado em $SetupExe"
}
$Hash = (Get-FileHash -Algorithm SHA256 -Path $SetupExe).Hash.ToLowerInvariant()
$ShaOut = "$SetupExe.sha256"
Set-Content -Path $ShaOut -Value "$Hash  Registrale-Setup-$Version.exe" -Encoding ASCII

Write-Host "==> Instalador gerado com sucesso:" -ForegroundColor Green
Write-Host "    $SetupExe"
Write-Host "    SHA-256: $Hash ($ShaOut)"
