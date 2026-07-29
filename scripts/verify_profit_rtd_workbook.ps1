param(
    [string]$WorkbookPath = "E:\gamma levels\profit_rtd.xlsx",
    [string]$PreviewDirectory = "E:\tmp\gamma_levels_verify"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Path $PreviewDirectory -Force | Out-Null

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$workbook = $null

try {
    $workbook = $excel.Workbooks.Open($WorkbookPath, 0, $true)
    $expectedSheets = @("Cadeia", "RTD_Profit", "Config")
    foreach ($name in $expectedSheets) {
        if ($null -eq $workbook.Worksheets.Item($name)) {
            throw "Planilha ausente: $name"
        }
    }

    $raw = $workbook.Worksheets.Item("RTD_Profit")
    $chain = $workbook.Worksheets.Item("Cadeia")
    $config = $workbook.Worksheets.Item("Config")
    $rawFormula = [string]$raw.Range("B2").Formula
    $chainFormula = [string]$chain.Range("B2").Formula
    $spotFormula = [string]$config.Range("B4").Formula
    if ($rawFormula -notmatch "RTDTrading.RTDServer") { throw "Fórmula RTD ausente em RTD_Profit!B2" }
    if ($spotFormula -notmatch "RTDTrading.RTDServer") { throw "Fórmula RTD ausente em Config!B4" }
    if ($chainFormula -notmatch "option|SEARCH|MID") { throw "Fórmula de tipo ausente em Cadeia!B2" }

    $previews = @(
        @{ Sheet = $config; Range = "A1:F22"; File = "config.png" },
        @{ Sheet = $raw; Range = "A1:P12"; File = "rtd_profit.png" },
        @{ Sheet = $chain; Range = "A1:R12"; File = "cadeia.png" }
    )
    foreach ($preview in $previews) {
        $preview.Sheet.Activate()
        $range = $preview.Sheet.Range($preview.Range)
        $range.CopyPicture(1, 2)
        $chartObject = $preview.Sheet.ChartObjects().Add(0, 0, $range.Width, $range.Height)
        $chartObject.Chart.Paste() | Out-Null
        $path = Join-Path $PreviewDirectory $preview.File
        if (-not $chartObject.Chart.Export($path, "PNG")) {
            throw "Falha ao renderizar $($preview.Sheet.Name)"
        }
        $chartObject.Delete()
    }

    Write-Output "Verificação concluída"
    Write-Output "RTD: $rawFormula"
    Write-Output "Tipo: $chainFormula"
    Write-Output "Spot: $spotFormula"
    Get-ChildItem -LiteralPath $PreviewDirectory | Select-Object Name, Length
}
finally {
    if ($null -ne $workbook) { $workbook.Close($false) }
    $excel.Quit()
}
