param(
    [string]$WorkbookPath = "E:\gamma levels\profit_rtd.xlsx"
)

$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

[ComImport, Guid("00000016-0000-0000-C000-000000000046"),
 InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IOleMessageFilter
{
    [PreserveSig] int HandleInComingCall(int callType, IntPtr taskCaller, int tickCount, IntPtr interfaceInfo);
    [PreserveSig] int RetryRejectedCall(IntPtr taskCallee, int tickCount, int rejectType);
    [PreserveSig] int MessagePending(IntPtr taskCallee, int tickCount, int pendingType);
}

public sealed class ExcelOleMessageFilter : IOleMessageFilter
{
    [DllImport("Ole32.dll")]
    private static extern int CoRegisterMessageFilter(IOleMessageFilter newFilter, out IOleMessageFilter oldFilter);
    private static IOleMessageFilter previous;

    public static void Register()
    {
        IOleMessageFilter oldFilter;
        CoRegisterMessageFilter(new ExcelOleMessageFilter(), out oldFilter);
        previous = oldFilter;
    }

    public static void Revoke()
    {
        IOleMessageFilter ignored;
        CoRegisterMessageFilter(previous, out ignored);
        previous = null;
    }

    public int HandleInComingCall(int callType, IntPtr taskCaller, int tickCount, IntPtr interfaceInfo) { return 0; }
    public int RetryRejectedCall(IntPtr taskCallee, int tickCount, int rejectType) { return rejectType == 2 ? 150 : -1; }
    public int MessagePending(IntPtr taskCallee, int tickCount, int pendingType) { return 2; }
}
'@

[ExcelOleMessageFilter]::Register()

function Get-ExcelColor([int]$Red, [int]$Green, [int]$Blue) {
    return $Red + (256 * $Green) + (65536 * $Blue)
}

. (Join-Path $PSScriptRoot "signals_workbook.ps1")

function Get-SummaryValue($Summary, [string]$Name) {
    $property = $Summary.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Get-FrameColumnIndex($Frame, [string]$Name) {
    $columns = @($Frame.columns)
    for ($index = 0; $index -lt $columns.Count; $index++) {
        if ([string]$columns[$index] -eq $Name) { return $index + 1 }
    }
    throw "Coluna nao encontrada no payload: $Name"
}

function Remove-ResultSheet($Workbook, [string]$Name) {
    for ($index = $Workbook.Worksheets.Count; $index -ge 1; $index--) {
        if ($Workbook.Worksheets.Item($index).Name -eq $Name) {
            $Workbook.Worksheets.Item($index).Delete()
            return
        }
    }
}

function Write-FrameSheet($Sheet, $Frame, [string]$TableName, [int]$HeaderColor, [int]$WhiteColor) {
    $columns = @($Frame.columns)
    $rows = @($Frame.rows)
    $columnCount = $columns.Count
    $rowCount = $rows.Count
    if ($columnCount -eq 0) { return }

    $matrix = [object[,]]::new($rowCount + 1, $columnCount)
    for ($column = 0; $column -lt $columnCount; $column++) {
        $matrix[0, $column] = [string]$columns[$column]
    }
    for ($row = 0; $row -lt $rowCount; $row++) {
        $values = @($rows[$row])
        for ($column = 0; $column -lt $columnCount; $column++) {
            $value = $values[$column]
            $matrix[($row + 1), $column] = Convert-ToExcelComValue $value
        }
    }

    $target = $Sheet.Range("A1").Resize($rowCount + 1, $columnCount)
    Set-ExcelRangeMatrix $target $matrix
    $Sheet.Range("A1").Resize(1, $columnCount).Interior.Color = $HeaderColor
    $Sheet.Range("A1").Resize(1, $columnCount).Font.Color = $WhiteColor
    $Sheet.Range("A1").Resize(1, $columnCount).Font.Bold = $true
    $Sheet.Range("A1").Resize(1, $columnCount).HorizontalAlignment = -4108

    if ($rowCount -gt 0) {
        $table = $Sheet.ListObjects.Add(1, $target, $null, 1)
        $table.Name = $TableName
        $table.TableStyle = "TableStyleMedium2"
    }

    for ($column = 0; $column -lt $columnCount; $column++) {
        $name = [string]$columns[$column]
        $range = $Sheet.Range($Sheet.Cells.Item(2, $column + 1), $Sheet.Cells.Item([Math]::Max(2, $rowCount + 1), $column + 1))
        if ($name -match 'expiration|valuation_date') {
            $range.NumberFormatLocal = "aaaa-mm-dd"
        }
        elseif ($name -match '(^|_)iv($|_)|implied_volatility|ratio|imbalance|share|percent|weight|score|delta$|gamma$|vega$|vanna$|charm$') {
            $range.NumberFormatLocal = "0,0000"
        }
        elseif ($name -match 'strike|spot|price|wall|level|center|pain|flip|zone|range|move|support|resistance') {
            $range.NumberFormatLocal = "0,00"
        }
        elseif ($name -match 'gex|dex|exposure|open_interest|oi_|volume|multiplier') {
            $range.NumberFormatLocal = "#.##0"
        }
    }

    $Sheet.Cells.Font.Name = "Aptos"
    $Sheet.Cells.Font.Size = 10
    $Sheet.Rows.Item(1).RowHeight = 24
    $Sheet.UsedRange.Columns.AutoFit() | Out-Null
    for ($column = 1; $column -le $columnCount; $column++) {
        if ($Sheet.Columns.Item($column).ColumnWidth -gt 24) {
            $Sheet.Columns.Item($column).ColumnWidth = 24
        }
        elseif ($Sheet.Columns.Item($column).ColumnWidth -lt 11) {
            $Sheet.Columns.Item($column).ColumnWidth = 11
        }
    }
}

function Add-Series($Chart, [string]$Name, $CategoryRange, $ValueRange, [int]$Color) {
    $series = $Chart.SeriesCollection().NewSeries()
    $series.Name = $Name
    $series.XValues = $CategoryRange
    $series.Values = $ValueRange
    $series.Format.Fill.ForeColor.RGB = $Color
    $series.Format.Line.ForeColor.RGB = $Color
    return $series
}

$navy = Get-ExcelColor 28 49 79
$teal = Get-ExcelColor 0 120 140
$green = Get-ExcelColor 46 125 50
$lightGreen = Get-ExcelColor 226 239 218
$red = Get-ExcelColor 192 0 0
$lightRed = Get-ExcelColor 244 204 204
$amber = Get-ExcelColor 191 144 0
$lightAmber = Get-ExcelColor 255 242 204
$lightBlue = Get-ExcelColor 221 235 247
$gray = Get-ExcelColor 242 242 242
$darkGray = Get-ExcelColor 89 89 89
$white = Get-ExcelColor 255 255 255

$resolvedWorkbookPath = [IO.Path]::GetFullPath($WorkbookPath)
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$payloadPath = Join-Path $projectRoot "resultado_excel\payload.json"
$catalogPath = Join-Path $projectRoot "series_autorizadas_b3.zip"

Add-Type -AssemblyName Microsoft.VisualBasic
try {
    $workbook = [Microsoft.VisualBasic.Interaction]::GetObject($resolvedWorkbookPath, $null)
    $excel = $workbook.Application
}
catch {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $true
    $workbook = $excel.Workbooks.Open($resolvedWorkbookPath)
}

$previousAlerts = $excel.DisplayAlerts
$previousUpdating = $excel.ScreenUpdating
$previousStatusBar = $excel.StatusBar
$previousCalculation = $excel.Calculation

try {
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false
    $excel.StatusBar = "Gamma Levels: atualizando dados do Profit..."
    $excel.Calculation = -4135

    $configSheet = $workbook.Worksheets.Item("Config")
    $signalParameters = Ensure-SignalConfiguration $workbook $configSheet $navy $teal $white $lightAmber $lightGreen
    $excel.CalculateFull()
    $workbook.Save()

    $valuationValue = $configSheet.Range("B8").Value2
    if ($valuationValue -is [double] -or $valuationValue -is [int]) {
        $valuationDate = [datetime]::FromOADate([double]$valuationValue).ToString("yyyy-MM-dd")
    }
    else {
        $valuationDate = ([datetime]$valuationValue).ToString("yyyy-MM-dd")
    }

    $excel.StatusBar = "Gamma Levels: executando os calculos..."
    Push-Location $projectRoot
    try {
        $pythonArguments = @(
            "-m", "gamma_levels.excel_results",
            "--workbook", $resolvedWorkbookPath,
            "--output", $payloadPath,
            "--valuation-date", $valuationDate,
            "--signal-strength-min", $signalParameters.StrengthMin,
            "--signal-rr-min", $signalParameters.RrMin,
            "--signal-horizon-days", $signalParameters.HorizonDays,
            "--signal-delta-min", $signalParameters.DeltaMin,
            "--signal-delta-max", $signalParameters.DeltaMax,
            "--signal-iv-shock", $signalParameters.IvShock,
            "--signal-buffer-step", $signalParameters.BufferStep,
            "--monitor-interval", $signalParameters.MonitorInterval
        )
        if (-not [string]::IsNullOrWhiteSpace($signalParameters.CallOverride)) {
            $pythonArguments += @("--signal-call-override", $signalParameters.CallOverride)
        }
        if (-not [string]::IsNullOrWhiteSpace($signalParameters.PutOverride)) {
            $pythonArguments += @("--signal-put-override", $signalParameters.PutOverride)
        }
        if (Test-Path -LiteralPath $catalogPath) {
            $pythonArguments += @("--b3-catalog", $catalogPath)
        }
        & python @pythonArguments
        if ($LASTEXITCODE -ne 0) {
            throw "O calculo Python terminou com codigo $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    $payload = Get-Content -LiteralPath $payloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $summary = $payload.summary
    $excel.Calculation = -4135
    Start-Sleep -Milliseconds 300

    foreach ($sheetName in @("Resultado", "Sinais", "Por_Strike", "Por_Vencimento", "Opcoes_Calculadas")) {
        Remove-ResultSheet $workbook $sheetName
    }

    $missing = [System.Reflection.Missing]::Value
    $resultSheet = $workbook.Worksheets.Add($missing, $workbook.Worksheets.Item($workbook.Worksheets.Count), 1, $missing)
    $resultSheet.Name = "Resultado"
    $signalsSheet = $workbook.Worksheets.Add($missing, $workbook.Worksheets.Item($workbook.Worksheets.Count), 1, $missing)
    $signalsSheet.Name = "Sinais"
    $strikeSheet = $workbook.Worksheets.Add($missing, $workbook.Worksheets.Item($workbook.Worksheets.Count), 1, $missing)
    $strikeSheet.Name = "Por_Strike"
    $expirySheet = $workbook.Worksheets.Add($missing, $workbook.Worksheets.Item($workbook.Worksheets.Count), 1, $missing)
    $expirySheet.Name = "Por_Vencimento"
    $optionsSheet = $workbook.Worksheets.Add($missing, $workbook.Worksheets.Item($workbook.Worksheets.Count), 1, $missing)
    $optionsSheet.Name = "Opcoes_Calculadas"
    $historySheet = Ensure-SignalHistorySheet $workbook $navy $white

    $excel.StatusBar = "Gamma Levels: montando as tabelas de auditoria..."
    Write-FrameSheet $strikeSheet $payload.by_strike "tblPorStrike" $navy $white
    Write-FrameSheet $expirySheet $payload.by_expiration "tblPorVencimento" $navy $white
    Write-FrameSheet $optionsSheet $payload.options "tblOpcoesCalculadas" $navy $white

    foreach ($detailSheet in @($strikeSheet, $expirySheet, $optionsSheet)) {
        $detailSheet.Activate()
        $excel.ActiveWindow.SplitRow = 1
        $excel.ActiveWindow.FreezePanes = $true
        $excel.ActiveWindow.DisplayGridlines = $false
        $excel.ActiveWindow.Zoom = 85
    }

    $excel.StatusBar = "Gamma Levels: montando o painel Resultado..."
    $resultSheet.Cells.Font.Name = "Aptos"
    $resultSheet.Cells.Font.Size = 10
    $resultSheet.Range("A1:N1").Merge()
    $underlyingTicker = [string]$configSheet.Range("B3").Value2
    $resultSheet.Range("A1").Value2 = "GAMMA LEVELS - RESULTADOS $underlyingTicker"
    $resultSheet.Range("A1:N1").Interior.Color = $navy
    $resultSheet.Range("A1:N1").Font.Color = $white
    $resultSheet.Range("A1:N1").Font.Bold = $true
    $resultSheet.Range("A1:N1").Font.Size = 17
    $resultSheet.Range("A1:N1").HorizontalAlignment = -4108
    $resultSheet.Rows.Item(1).RowHeight = 30

    $resultSheet.Range("A2:N2").Merge()
    $resultSheet.Range("A2").Value2 = "Atualizado em $($payload.generated_at) | $($payload.quality.calculated_rows) opcoes | $($payload.quality.imputed_iv_count) IVs interpoladas | Fonte: B3 + Profit RTD"
    $resultSheet.Range("A2:N2").Font.Color = $darkGray
    $resultSheet.Range("A2:N2").HorizontalAlignment = -4108

    $cardPairs = @(@("A","B"), @("C","D"), @("E","F"), @("G","H"), @("I","J"), @("K","L"), @("M","N"))
    $cardLabels = @("SPOT", "GAMMA FLIP", "CALL WALL", "PUT WALL", "GAMMA MAGNET", "MAX PAIN", "REGIME")
    $cardValues = @(
        (Get-SummaryValue $summary "spot"),
        (Get-SummaryValue $summary "gamma_flip"),
        (Get-SummaryValue $summary "call_wall"),
        (Get-SummaryValue $summary "put_wall"),
        (Get-SummaryValue $summary "gamma_magnet"),
        (Get-SummaryValue $summary "max_pain"),
        $payload.regime
    )
    for ($index = 0; $index -lt $cardPairs.Count; $index++) {
        $left = $cardPairs[$index][0]
        $right = $cardPairs[$index][1]
        $labelRange = $resultSheet.Range("${left}4:${right}4")
        $valueRange = $resultSheet.Range("${left}5:${right}5")
        $labelRange.Merge()
        $valueRange.Merge()
        Set-ExcelScalarValue $labelRange $cardLabels[$index]
        Set-ExcelScalarValue $valueRange $(if ($null -eq $cardValues[$index]) { "n/d" } else { $cardValues[$index] })
        $labelRange.Interior.Color = $teal
        $labelRange.Font.Color = $white
        $labelRange.Font.Bold = $true
        $valueRange.Interior.Color = $lightBlue
        $valueRange.Font.Bold = $true
        $valueRange.Font.Size = 13
        $labelRange.HorizontalAlignment = -4108
        $valueRange.HorizontalAlignment = -4108
        if ($index -lt 6) { $valueRange.NumberFormatLocal = "0,00" }
    }
    $resultSheet.Range("M5:N5").Interior.Color = if ((Get-SummaryValue $summary "gex_total") -ge 0) { $lightGreen } else { $lightRed }
    $resultSheet.Range("M5:N5").Font.Color = if ((Get-SummaryValue $summary "gex_total") -ge 0) { $green } else { $red }
    $resultSheet.Rows.Item(4).RowHeight = 20
    $resultSheet.Rows.Item(5).RowHeight = 28

    $resultSheet.Range("A7:B7").Merge()
    $resultSheet.Range("C7:D7").Merge()
    $resultSheet.Range("E7:F7").Merge()
    $resultSheet.Range("A7").Value2 = "FAIXAS ESPERADAS"
    $resultSheet.Range("C7").Value2 = "INFERIOR"
    $resultSheet.Range("E7").Value2 = "SUPERIOR"
    $resultSheet.Range("H7:N7").Merge()
    $resultSheet.Range("H7").Value2 = "NIVEIS DIRECIONAIS"
    $resultSheet.Range("A7:F7").Interior.Color = $teal
    $resultSheet.Range("H7:N7").Interior.Color = $teal
    $resultSheet.Range("A7:F7").Font.Color = $white
    $resultSheet.Range("H7:N7").Font.Color = $white
    $resultSheet.Range("A7:F7").Font.Bold = $true
    $resultSheet.Range("H7:N7").Font.Bold = $true

    $rangeRows = @(
        @("Expected Move - IV", "expected_move_iv_lower", "expected_move_iv_upper"),
        @("Expected Move - Straddle", "expected_move_straddle_lower", "expected_move_straddle_upper"),
        @("Faixa +/-0,5 sigma", "range_half_sigma", "range_half_sigma"),
        @("Faixa +/-1 sigma", "range_one_sigma", "range_one_sigma"),
        @("Faixa +/-2 sigma", "range_two_sigma", "range_two_sigma")
    )
    for ($index = 0; $index -lt $rangeRows.Count; $index++) {
        $row = 8 + $index
        $resultSheet.Range("A${row}:B${row}").Merge()
        $resultSheet.Range("C${row}:D${row}").Merge()
        $resultSheet.Range("E${row}:F${row}").Merge()
        Set-ExcelScalarValue $resultSheet.Range("A${row}") $rangeRows[$index][0]
        if ($index -lt 2) {
            $low = Get-SummaryValue $summary $rangeRows[$index][1]
            $high = Get-SummaryValue $summary $rangeRows[$index][2]
        }
        else {
            $pair = @(Get-SummaryValue $summary $rangeRows[$index][1])
            $low = if ($pair.Count -gt 0) { $pair[0] } else { $null }
            $high = if ($pair.Count -gt 1) { $pair[1] } else { $null }
        }
        Set-ExcelScalarValue $resultSheet.Range("C${row}") $(if ($null -eq $low) { "n/d" } else { $low })
        Set-ExcelScalarValue $resultSheet.Range("E${row}") $(if ($null -eq $high) { "n/d" } else { $high })
        $resultSheet.Range("C${row}:F${row}").NumberFormatLocal = "0,00"
    }
    $directionRows = @(
        @("Suportes", ((@(Get-SummaryValue $summary "support_levels") | ForEach-Object { "{0:N2}" -f $_ }) -join " / ")),
        @("Resistencias", ((@(Get-SummaryValue $summary "resistance_levels") | ForEach-Object { "{0:N2}" -f $_ }) -join " / ")),
        @("Resistencia Call", (Get-SummaryValue $summary "call_resistance_level")),
        @("Suporte Put", (Get-SummaryValue $summary "put_support_level")),
        @("Delta / Vanna / Charm", ("{0:N2} / {1:N2} / {2:N2}" -f (Get-SummaryValue $summary "delta_wall"), (Get-SummaryValue $summary "vanna_level"), (Get-SummaryValue $summary "charm_level")))
    )
    for ($index = 0; $index -lt $directionRows.Count; $index++) {
        $row = 8 + $index
        $resultSheet.Range("H${row}:J${row}").Merge()
        $resultSheet.Range("K${row}:N${row}").Merge()
        Set-ExcelScalarValue $resultSheet.Range("H${row}") $directionRows[$index][0]
        Set-ExcelScalarValue $resultSheet.Range("K${row}") $(if ($null -eq $directionRows[$index][1] -or [string]::IsNullOrWhiteSpace([string]$directionRows[$index][1])) { "n/d" } else { $directionRows[$index][1] })
        if ($index -ge 2 -and $index -le 3) { $resultSheet.Range("K${row}:N${row}").NumberFormatLocal = "0,00" }
    }
    $resultSheet.Range("A8:F12").Borders.LineStyle = 1
    $resultSheet.Range("H8:N12").Borders.LineStyle = 1
    $resultSheet.Range("A8:B12").Interior.Color = $gray
    $resultSheet.Range("H8:J12").Interior.Color = $gray

    $resultSheet.Range("A14:F14").Merge()
    $resultSheet.Range("A14").Value2 = "EXPOSICOES E CONCENTRACAO"
    $resultSheet.Range("H14:N14").Merge()
    $resultSheet.Range("H14").Value2 = "QUALIDADE E AUDITORIA"
    $resultSheet.Range("A14:F14").Interior.Color = $teal
    $resultSheet.Range("H14:N14").Interior.Color = $teal
    $resultSheet.Range("A14:F14").Font.Color = $white
    $resultSheet.Range("H14:N14").Font.Color = $white
    $resultSheet.Range("A14:F14").Font.Bold = $true
    $resultSheet.Range("H14:N14").Font.Bold = $true

    $exposureRows = @(
        @("GEX total", "gex_total", "GEX Calls", "gex_call"),
        @("GEX Puts", "gex_put", "Imbalance", "gamma_imbalance"),
        @("Put/Call Gamma", "put_call_gamma_ratio", "Concentracao Top 3", "gamma_concentration_top3"),
        @("Centro Gamma", "gamma_center", "Centro Call", "call_gamma_center"),
        @("Centro Put", "put_gamma_center", "OI Wall total", "oi_total_wall"),
        @("Nivel Dealer", "dealer_exposure_level", "Volume/OI", "volume_oi_level"),
        @("Strike ATM", "atm_strike", "IV ATM", "atm_iv")
    )
    for ($index = 0; $index -lt $exposureRows.Count; $index++) {
        $row = 15 + $index
        $resultSheet.Range("A${row}:B${row}").Merge()
        $resultSheet.Range("D${row}:E${row}").Merge()
        Set-ExcelScalarValue $resultSheet.Range("A${row}") $exposureRows[$index][0]
        Set-ExcelScalarValue $resultSheet.Range("C${row}") $(Get-SummaryValue $summary $exposureRows[$index][1])
        Set-ExcelScalarValue $resultSheet.Range("D${row}") $exposureRows[$index][2]
        Set-ExcelScalarValue $resultSheet.Range("F${row}") $(Get-SummaryValue $summary $exposureRows[$index][3])
        $leftKey = $exposureRows[$index][1]
        $rightKey = $exposureRows[$index][3]
        $leftFormat = if ($leftKey -match '^gex') { "#.##0" } elseif ($leftKey -match 'ratio|imbalance|concentration|atm_iv') { "0,0000" } else { "0,00" }
        $rightFormat = if ($rightKey -match '^gex') { "#.##0" } elseif ($rightKey -match 'ratio|imbalance|concentration|atm_iv') { "0,0000" } else { "0,00" }
        $resultSheet.Range("C${row}").NumberFormatLocal = $leftFormat
        $resultSheet.Range("F${row}").NumberFormatLocal = $rightFormat
    }
    $resultSheet.Range("A15:B21").Interior.Color = $gray
    $resultSheet.Range("D15:E21").Interior.Color = $gray
    $resultSheet.Range("A15:F21").Borders.LineStyle = 1

    $checks = @($payload.checks)
    for ($index = 0; $index -lt $checks.Count; $index++) {
        $row = 15 + $index
        $resultSheet.Range("H${row}:J${row}").Merge()
        $resultSheet.Range("K${row}:L${row}").Merge()
        $resultSheet.Range("M${row}:N${row}").Merge()
        Set-ExcelScalarValue $resultSheet.Range("H${row}") $checks[$index].check
        Set-ExcelScalarValue $resultSheet.Range("K${row}") $checks[$index].status
        Set-ExcelScalarValue $resultSheet.Range("M${row}") $checks[$index].detail
        $statusRange = $resultSheet.Range("K${row}:L${row}")
        if ($checks[$index].status -eq "OK") {
            $statusRange.Interior.Color = $lightGreen
            $statusRange.Font.Color = $green
        }
        elseif ($checks[$index].status -eq "AVISO") {
            $statusRange.Interior.Color = $lightAmber
            $statusRange.Font.Color = $amber
        }
        else {
            $statusRange.Interior.Color = $lightRed
            $statusRange.Font.Color = $red
        }
        $statusRange.Font.Bold = $true
        $statusRange.HorizontalAlignment = -4108
    }
    $resultSheet.Range("H15:J21").Interior.Color = $gray
    $resultSheet.Range("H15:N21").Borders.LineStyle = 1

    $resultSheet.Range("A24:H24").Merge()
    $resultSheet.Range("A24").Value2 = "RESUMO POR VENCIMENTO"
    $resultSheet.Range("I24:N24").Merge()
    $resultSheet.Range("I24").Value2 = "PRINCIPAIS GAMMA LEVELS"
    $resultSheet.Range("A24:H24").Interior.Color = $teal
    $resultSheet.Range("I24:N24").Interior.Color = $teal
    $resultSheet.Range("A24:H24").Font.Color = $white
    $resultSheet.Range("I24:N24").Font.Color = $white
    $resultSheet.Range("A24:H24").Font.Bold = $true
    $resultSheet.Range("I24:N24").Font.Bold = $true

    $expiryHeaders = @("Vencimento", "DTE", "GEX total", "GEX Call", "GEX Put", "Gamma Flip", "Max Pain", "Move IV")
    for ($column = 0; $column -lt $expiryHeaders.Count; $column++) {
        Set-ExcelScalarValue $resultSheet.Cells.Item(25, $column + 1) $expiryHeaders[$column]
    }
    $expiryKeys = @("expiration", "days_to_expiry", "gex_total", "gex_call", "gex_put", "gamma_flip", "max_pain", "expected_move_iv")
    $expiryColumns = @($payload.by_expiration.columns)
    $expiryRows = @($payload.by_expiration.rows)
    for ($rowIndex = 0; $rowIndex -lt $expiryRows.Count; $rowIndex++) {
        $rowValues = @($expiryRows[$rowIndex])
        for ($column = 0; $column -lt $expiryKeys.Count; $column++) {
            $sourceIndex = [Array]::IndexOf($expiryColumns, $expiryKeys[$column])
            Set-ExcelScalarValue $resultSheet.Cells.Item(26 + $rowIndex, 1 + $column) $(if ($sourceIndex -ge 0) { $rowValues[$sourceIndex] } else { $null })
        }
    }
    $resultSheet.Range("A25:H25").Interior.Color = $navy
    $resultSheet.Range("A25:H25").Font.Color = $white
    $resultSheet.Range("A25:H25").Font.Bold = $true
    if ($expiryRows.Count -gt 0) {
        $expiryLastRow = 25 + $expiryRows.Count
        $resultSheet.Range("B26:B$expiryLastRow").NumberFormatLocal = "0"
        $resultSheet.Range("C26:E$expiryLastRow").NumberFormatLocal = "#.##0"
        $resultSheet.Range("F26:H$expiryLastRow").NumberFormatLocal = "0,00"
    }

    $topHeaders = @("Strike", "Dist. %", "GEX Call", "GEX Put", "GEX Liq.", "Zona")
    for ($column = 0; $column -lt $topHeaders.Count; $column++) {
        Set-ExcelScalarValue $resultSheet.Cells.Item(25, 9 + $column) $topHeaders[$column]
    }
    $topColumns = @($payload.top_levels.columns)
    $topRows = @($payload.top_levels.rows)
    $topKeys = @("strike", "distance_percent", "gex_call", "gex_put", "gex_net")
    for ($rowIndex = 0; $rowIndex -lt $topRows.Count; $rowIndex++) {
        $rowValues = @($topRows[$rowIndex])
        for ($column = 0; $column -lt $topKeys.Count; $column++) {
            $sourceIndex = [Array]::IndexOf($topColumns, $topKeys[$column])
            Set-ExcelScalarValue $resultSheet.Cells.Item(26 + $rowIndex, 9 + $column) $(if ($sourceIndex -ge 0) { $rowValues[$sourceIndex] } else { $null })
        }
        $lowIndex = [Array]::IndexOf($topColumns, "zone_low")
        $highIndex = [Array]::IndexOf($topColumns, "zone_high")
        $low = if ($lowIndex -ge 0) { $rowValues[$lowIndex] } else { $null }
        $high = if ($highIndex -ge 0) { $rowValues[$highIndex] } else { $null }
        Set-ExcelScalarValue $resultSheet.Cells.Item(26 + $rowIndex, 14) $(if ($null -ne $low -and $null -ne $high) { "{0:N2}-{1:N2}" -f $low, $high } else { "n/d" })
    }
    $resultSheet.Range("I25:N25").Interior.Color = $navy
    $resultSheet.Range("I25:N25").Font.Color = $white
    $resultSheet.Range("I25:N25").Font.Bold = $true
    if ($topRows.Count -gt 0) {
        $topLastRow = 25 + $topRows.Count
        $resultSheet.Range("I26:J$topLastRow").NumberFormatLocal = "0,00"
        $resultSheet.Range("K26:M$topLastRow").NumberFormatLocal = "#.##0"
    }

    $resultSheet.Range("A25:H$([Math]::Max(26, 25 + $expiryRows.Count))").Borders.LineStyle = 1
    $resultSheet.Range("I25:N$([Math]::Max(26, 25 + $topRows.Count))").Borders.LineStyle = 1

    # Grafico 1 - GEX Call e Put por strike.
    $strikeCount = @($payload.by_strike.rows).Count
    $strikeColumn = Get-FrameColumnIndex $payload.by_strike "strike"
    $gexCallColumn = Get-FrameColumnIndex $payload.by_strike "gex_call"
    $gexPutColumn = Get-FrameColumnIndex $payload.by_strike "gex_put"
    $left = $resultSheet.Range("A38").Left
    $top = $resultSheet.Range("A38").Top
    $width = ($resultSheet.Range("G53").Left + $resultSheet.Range("G53").Width) - $left
    $height = ($resultSheet.Range("G53").Top + $resultSheet.Range("G53").Height) - $top
    $chartObject = $resultSheet.ChartObjects().Add($left, $top, $width, $height)
    $chart = $chartObject.Chart
    $chart.ChartType = 51
    $categories = $strikeSheet.Range($strikeSheet.Cells.Item(2, $strikeColumn), $strikeSheet.Cells.Item($strikeCount + 1, $strikeColumn))
    [void](Add-Series $chart "GEX Call" $categories $strikeSheet.Range($strikeSheet.Cells.Item(2, $gexCallColumn), $strikeSheet.Cells.Item($strikeCount + 1, $gexCallColumn)) $teal)
    [void](Add-Series $chart "GEX Put" $categories $strikeSheet.Range($strikeSheet.Cells.Item(2, $gexPutColumn), $strikeSheet.Cells.Item($strikeCount + 1, $gexPutColumn)) $red)
    $chart.HasTitle = $true
    $chart.ChartTitle.Text = "GEX por strike"
    $chart.HasLegend = $true
    $chart.Legend.Position = -4107
    $chart.Axes(1).CategoryType = 2
    $chart.Axes(1).TickLabelSpacing = 2

    # Grafico 2 - decomposicao do GEX por vencimento.
    $expiryCount = @($payload.by_expiration.rows).Count
    $expiryColumn = Get-FrameColumnIndex $payload.by_expiration "expiration"
    $expiryTotalColumn = Get-FrameColumnIndex $payload.by_expiration "gex_total"
    $expiryCallColumn = Get-FrameColumnIndex $payload.by_expiration "gex_call"
    $expiryPutColumn = Get-FrameColumnIndex $payload.by_expiration "gex_put"
    $left = $resultSheet.Range("H38").Left
    $top = $resultSheet.Range("H38").Top
    $width = ($resultSheet.Range("N53").Left + $resultSheet.Range("N53").Width) - $left
    $height = ($resultSheet.Range("N53").Top + $resultSheet.Range("N53").Height) - $top
    $chartObject = $resultSheet.ChartObjects().Add($left, $top, $width, $height)
    $chart = $chartObject.Chart
    $chart.ChartType = 51
    $categories = $expirySheet.Range($expirySheet.Cells.Item(2, $expiryColumn), $expirySheet.Cells.Item($expiryCount + 1, $expiryColumn))
    [void](Add-Series $chart "GEX total" $categories $expirySheet.Range($expirySheet.Cells.Item(2, $expiryTotalColumn), $expirySheet.Cells.Item($expiryCount + 1, $expiryTotalColumn)) $navy)
    [void](Add-Series $chart "GEX Call" $categories $expirySheet.Range($expirySheet.Cells.Item(2, $expiryCallColumn), $expirySheet.Cells.Item($expiryCount + 1, $expiryCallColumn)) $teal)
    [void](Add-Series $chart "GEX Put" $categories $expirySheet.Range($expirySheet.Cells.Item(2, $expiryPutColumn), $expirySheet.Cells.Item($expiryCount + 1, $expiryPutColumn)) $red)
    $chart.HasTitle = $true
    $chart.ChartTitle.Text = "GEX por vencimento"
    $chart.HasLegend = $true
    $chart.Legend.Position = -4107
    $chart.Axes(1).CategoryType = 2

    $resultSheet.Range("A55:N55").Merge()
    $resultSheet.Range("A55").Value2 = "NOTAS E CONVENCOES"
    $resultSheet.Range("A55:N55").Interior.Color = $teal
    $resultSheet.Range("A55:N55").Font.Color = $white
    $resultSheet.Range("A55:N55").Font.Bold = $true
    $resultSheet.Range("A56:N58").Merge()
    $resultSheet.Range("A56").Value2 = "Fonte: lista de series autorizadas da B3 e dados RTD do Profit. GEX usa call positiva e put negativa. Delta, gamma e vega do Profit sao preservadas; vanna e charm sao estimadas por Black-Scholes-Merton. IVs zeradas sao interpoladas no mesmo vencimento e tipo e ficam sinalizadas em Opcoes_Calculadas. Os niveis sao apoio analitico e nao garantia de preco ou recomendacao de investimento."
    $resultSheet.Range("A56:N58").WrapText = $true
    $resultSheet.Range("A56:N58").VerticalAlignment = -4160
    $resultSheet.Range("A56:N58").Interior.Color = $lightAmber
    $resultSheet.Rows.Item(56).RowHeight = 22
    $resultSheet.Rows.Item(57).RowHeight = 22
    $resultSheet.Rows.Item(58).RowHeight = 22

    $resultSheet.Columns.Item("A").ColumnWidth = 14
    $resultSheet.Columns.Item("B").ColumnWidth = 10
    $resultSheet.Range("C:N").ColumnWidth = 12
    $resultSheet.Columns.Item("C").ColumnWidth = 18
    $resultSheet.Columns.Item("D").ColumnWidth = 16
    $resultSheet.Columns.Item("E").ColumnWidth = 16
    $resultSheet.Columns.Item("F").ColumnWidth = 18
    $resultSheet.Range("A1:N58").VerticalAlignment = -4108
    $resultSheet.Range("A1:N58").Borders.Color = Get-ExcelColor 217 217 217
    $resultSheet.Activate()
    $excel.ActiveWindow.DisplayGridlines = $false
    $excel.ActiveWindow.Zoom = 85
    $excel.ActiveWindow.SplitRow = 2
    $excel.ActiveWindow.FreezePanes = $true
    $resultSheet.Range("A1").Select() | Out-Null

    $resultSheet.PageSetup.PrintArea = '$A$1:$N$58'
    $resultSheet.PageSetup.Orientation = 2
    $resultSheet.PageSetup.PaperSize = 8
    $resultSheet.PageSetup.Zoom = $false
    $resultSheet.PageSetup.FitToPagesWide = 1
    $resultSheet.PageSetup.FitToPagesTall = 1

    $excel.StatusBar = "Gamma Levels: montando sinais e monitor..."
    Build-SignalsSheet $signalsSheet $payload $configSheet $navy $teal $white $gray $lightBlue $lightGreen $lightAmber $lightRed $green $amber $red
    $historySheet.Activate()
    $excel.ActiveWindow.DisplayGridlines = $false
    $excel.ActiveWindow.SplitRow = 1
    $excel.ActiveWindow.FreezePanes = $true
    $excel.ActiveWindow.Zoom = 80
    $signalsSheet.Activate()
    $excel.ActiveWindow.DisplayGridlines = $false
    $excel.ActiveWindow.SplitRow = 17
    $excel.ActiveWindow.SplitColumn = 5
    $excel.ActiveWindow.FreezePanes = $true
    $signalsSheet.Range("A1").Select() | Out-Null

    if ($signalParameters.MonitorEnabled -match '^(?i)SIM$') {
        $configSheet.Range("I11").Value2 = "INICIANDO"
    }
    else {
        $configSheet.Range("I11").Value2 = "DESATIVADO"
    }

    $workbook.Save()
    if ($signalParameters.MonitorEnabled -match '^(?i)SIM$') {
        $monitorScript = Join-Path $PSScriptRoot "monitor_signals.ps1"
        $monitorArguments = @(
            "-STA", "-NoProfile", "-File", "`"$monitorScript`"",
            "-WorkbookPath", "`"$resolvedWorkbookPath`"",
            "-IntervalSeconds", [string]$signalParameters.MonitorInterval
        )
        [void](Start-Process -FilePath "pwsh.exe" -ArgumentList $monitorArguments -WindowStyle Hidden)
    }
    $excel.StatusBar = $false
    Write-Output "Aba Resultado criada e planilha salva: $($workbook.FullName)"
    Write-Output "Opcoes calculadas: $($payload.quality.calculated_rows)"
    Write-Output "IVs interpoladas: $($payload.quality.imputed_iv_count)"
    Write-Output "Sinais criados: $(@($payload.signals.rows).Count)"
    Write-Output "Strikes/vencimentos corrigidos pela B3: $($payload.quality.strike_recovered_count)/$($payload.quality.expiration_recovered_count)"
}
finally {
    $excel.DisplayAlerts = $previousAlerts
    $excel.ScreenUpdating = $previousUpdating
    $excel.StatusBar = $previousStatusBar
    $excel.Calculation = $previousCalculation
    [ExcelOleMessageFilter]::Revoke()
}
