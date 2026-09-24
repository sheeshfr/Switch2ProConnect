param(
    [Parameter(Mandatory=$true)]
    [string]$Path
)

if (-not (Test-Path $Path)) {
    Write-Error "File not found: $Path"
    exit 1
}

$content = [System.IO.File]::ReadAllText($Path)
$settings = @(
    'driver_installed',
    'hidhide_install_prompt_suppressed',
    'hidhide_installed',
    'start_minimized'
)

foreach ($setting in $settings) {
    $pattern = '(?m)^' + [regex]::Escape($setting) + ':\s*(true|false)\s*$'
    if ($content -match $pattern) {
        $content = [regex]::Replace($content, $pattern, ($setting + ': false'))
    }
}

# Clear any game_mappings
if ($content -match '(?ms)^game_mappings:.*?(?=^[a-zA-Z0-9_]+:|\Z)') {
    $content = [regex]::Replace($content, '(?ms)^game_mappings:.*?(?=^[a-zA-Z0-9_]+:|\Z)', "game_mappings: {`r`n}`r`n")
}

[System.IO.File]::WriteAllText($Path, $content, [System.Text.UTF8Encoding]::new($false))
