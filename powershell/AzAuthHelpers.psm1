$script:AzAuthCore = Join-Path $PSScriptRoot '../functions/az-auth-core.cjs'

function Invoke-AzAuthCore {
    param([string]$Operation, [string]$Manager, [object[]]$Arguments)
    if (-not (Test-Path -LiteralPath $script:AzAuthCore -PathType Leaf)) {
        $global:LASTEXITCODE = 127
        Write-Error 'az-auth-core is required. Reinstall the checkout. See README.md.'
        return
    }
    $node = Get-Command node -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $node) {
        $global:LASTEXITCODE = 127
        Write-Error 'Node 22 or newer is required. Install Node on PATH. See README.md.'
        return
    }
    $PSNativeCommandArgumentPassing = 'Standard'
    $coreArgs = @($script:AzAuthCore, $Operation)
    if ($Operation -eq 'write-npm') {
        $coreArgs += @('--') + $Arguments
    } else {
        $coreArgs += @('--manager', $Manager, '--') + $Arguments
    }
    if ($IsWindows) {
        & $node.Source @coreArgs
        $global:LASTEXITCODE = $LASTEXITCODE
    } else {
        # PowerShell expands unquoted splatted wildcards on Unix.
        $start = [System.Diagnostics.ProcessStartInfo]::new()
        $start.FileName = $node.Source
        $start.UseShellExecute = $false
        $start.WorkingDirectory = (Get-Location).ProviderPath
        foreach ($argument in $coreArgs) {
            $start.ArgumentList.Add([string]$argument)
        }
        try {
            $process = [System.Diagnostics.Process]::Start($start)
        } catch {
            $global:LASTEXITCODE = 1
            Write-Error "Cannot start Node. $($_.Exception.Message)"
            return
        }
        try {
            $process.WaitForExit()
            $global:LASTEXITCODE = $process.ExitCode
        } finally {
            $process.Dispose()
        }
    }
}

function npm { Invoke-AzAuthCore run npm $args }
function npx { Invoke-AzAuthCore run npx $args }
function pnpm { Invoke-AzAuthCore run pnpm $args }
function pnpx { Invoke-AzAuthCore run pnpx $args }
function pn { Invoke-AzAuthCore run pnpm $args }
function yarn { Invoke-AzAuthCore run yarn $args }
function bun { Invoke-AzAuthCore run bun $args }
function corepack { Invoke-AzAuthCore run corepack $args }
function dotnet { Invoke-AzAuthCore run dotnet $args }
function nuget { Invoke-AzAuthCore run nuget $args }
function rush { Invoke-AzAuthCore run rush $args }
function Invoke-RushPnpm { Invoke-AzAuthCore run rush-pnpm $args }
function write-npm {
    if ($args.Count -eq 0) {
        Invoke-AzAuthCore write-npm '' @('--from-project')
    } elseif ($args.Count -eq 1 -and $args[0] -in @('-Help', '--help')) {
        'Usage: write-npm [FEED [USER [EMAIL]]]. With no arguments, read the project .npmrc and prompt before replacing user authentication entries.'
    } else {
        Invoke-AzAuthCore write-npm '' $args
    }
}

Set-Alias -Name rush-pnpm -Value Invoke-RushPnpm
Export-ModuleMember -Function npm,npx,pnpm,pnpx,pn,yarn,bun,corepack,dotnet,nuget,rush,Invoke-RushPnpm,write-npm -Alias rush-pnpm
