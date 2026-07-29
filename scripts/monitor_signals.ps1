param(
    [string]$WorkbookPath = "E:\gamma levels\profit_rtd.xlsx",
    [int]$IntervalSeconds = 60
)

$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
[ComImport, Guid("00000016-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface ISignalMonitorMessageFilter
{
    [PreserveSig] int HandleInComingCall(int callType, IntPtr taskCaller, int tickCount, IntPtr interfaceInfo);
    [PreserveSig] int RetryRejectedCall(IntPtr taskCallee, int tickCount, int rejectType);
    [PreserveSig] int MessagePending(IntPtr taskCallee, int tickCount, int pendingType);
}
public sealed class SignalMonitorMessageFilter : ISignalMonitorMessageFilter
{
    [DllImport("Ole32.dll")]
    private static extern int CoRegisterMessageFilter(ISignalMonitorMessageFilter newFilter, out ISignalMonitorMessageFilter oldFilter);
    private static ISignalMonitorMessageFilter previous;
    public static void Register() { ISignalMonitorMessageFilter oldFilter; CoRegisterMessageFilter(new SignalMonitorMessageFilter(), out oldFilter); previous = oldFilter; }
    public static void Revoke() { ISignalMonitorMessageFilter ignored; CoRegisterMessageFilter(previous, out ignored); previous = null; }
    public int HandleInComingCall(int callType, IntPtr taskCaller, int tickCount, IntPtr interfaceInfo) { return 0; }
    public int RetryRejectedCall(IntPtr taskCallee, int tickCount, int rejectType) { return rejectType == 2 ? 200 : -1; }
    public int MessagePending(IntPtr taskCallee, int tickCount, int pendingType) { return 2; }
}
'@

. (Join-Path $PSScriptRoot "signals_workbook.ps1")

function Get-TableMap($Table) {
    $map = @{}
    $headers = $Table.HeaderRowRange.Value2
    for ($column = 1; $column -le $Table.ListColumns.Count; $column++) {
        $map[[string]$headers[1, $column]] = $column
    }
    return $map
}

function Get-ListValue($ListRow, $Map, [string]$Name) {
    if (-not $Map.ContainsKey($Name)) { return $null }
    return $ListRow.Range.Cells.Item(1, $Map[$Name]).Value2
}

function Set-ListValue($ListRow, $Map, [string]$Name, $Value) {
    if ($Map.ContainsKey($Name)) {
        $cell = $ListRow.Range.Cells.Item(1, $Map[$Name])
        Set-ExcelScalarValue $cell $Value
    }
}

function Set-SignalStateAppearance($SignalRow, $SignalMap) {
    $stateCell = $SignalRow.Range.Cells.Item(1, $SignalMap["Estado"])
    $state = [string]$stateCell.Value2
    $stateCell.Font.Bold = $true
    switch ($state) {
        "ACIONADO" { $stateCell.Interior.Color = 14348258; $stateCell.Font.Color = 3308846 }
        "ARMADO" { $stateCell.Interior.Color = 13431551; $stateCell.Font.Color = 37055 }
        "INVALIDADO" { $stateCell.Interior.Color = 13421812; $stateCell.Font.Color = 192 }
        default { $stateCell.Interior.Pattern = -4142; $stateCell.Font.Color = 0 }
    }
}

function Get-LiveOptionPrice($RawSheet, [string]$Ticker) {
    if ([string]::IsNullOrWhiteSpace($Ticker)) { return $null }
    $found = $RawSheet.Columns.Item(1).Find($Ticker)
    if ($null -eq $found) { return $null }
    $row = $found.Row
    $last = [double]$RawSheet.Cells.Item($row, 2).Value2
    $bid = [double]$RawSheet.Cells.Item($row, 3).Value2
    $ask = [double]$RawSheet.Cells.Item($row, 4).Value2
    if ($bid -gt 0 -and $ask -ge $bid) { return ($bid + $ask) / 2.0 }
    if ($last -gt 0) { return $last }
    return $null
}

function Add-HistorySignal($HistoryTable, $HistoryMap, $SignalRow, $SignalMap, [double]$DayHigh, [double]$DayLow) {
    $row = $HistoryTable.ListRows.Add()
    $now = [datetime]::Now
    $copyMap = @{
        "signal_id" = "signal_id"; "direction" = "Direcao"; "setup" = "Setup"; "level" = "Nivel";
        "zone_low" = "Zona Inf"; "zone_high" = "Zona Sup"; "strength" = "Forca"; "trigger" = "Gatilho";
        "invalidation" = "Invalidacao"; "target_1" = "T1"; "target_2" = "T2"; "target_3" = "T3";
        "target_1_asset_pct" = "Ativo T1 %"; "target_2_asset_pct" = "Ativo T2 %"; "target_3_asset_pct" = "Ativo T3 %";
        "ticker" = "Ticker Usado"; "option_entry_price" = "Preco Opcao"; "option_iv_source" = "IV Fonte";
        "option_proj_1_low" = "Opcao T1 Baixa %"; "option_proj_1_base" = "Opcao T1 Base %"; "option_proj_1_high" = "Opcao T1 Alta %";
        "option_proj_2_low" = "Opcao T2 Baixa %"; "option_proj_2_base" = "Opcao T2 Base %"; "option_proj_2_high" = "Opcao T2 Alta %";
        "option_proj_3_low" = "Opcao T3 Baixa %"; "option_proj_3_base" = "Opcao T3 Base %"; "option_proj_3_high" = "Opcao T3 Alta %"
    }
    foreach ($targetName in $copyMap.Keys) {
        Set-ListValue $row $HistoryMap $targetName (Get-ListValue $SignalRow $SignalMap $copyMap[$targetName])
    }
    Set-ListValue $row $HistoryMap "session_date" $now.Date
    Set-ListValue $row $HistoryMap "activated_at" $now
    Set-ListValue $row $HistoryMap "option_price_source" (Get-ListValue $SignalRow $SignalMap "Selecao")
    Set-ListValue $row $HistoryMap "activation_day_high" $DayHigh
    Set-ListValue $row $HistoryMap "activation_day_low" $DayLow
    Set-ListValue $row $HistoryMap "last_seen_high" $DayHigh
    Set-ListValue $row $HistoryMap "last_seen_low" $DayLow
    Set-ListValue $row $HistoryMap "ambiguity_flag" ""
    Set-ListValue $row $HistoryMap "data_quality" (Get-ListValue $SignalRow $SignalMap "IV Fonte")
    return $row
}

$resolvedPath = [IO.Path]::GetFullPath($WorkbookPath)
$hashBytes = [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($resolvedPath.ToLowerInvariant()))
$mutexName = "Local\GammaLevelsSignals_" + ([Convert]::ToHexString($hashBytes).Substring(0, 20))
$mutex = New-Object Threading.Mutex($false, $mutexName)
$ownsMutex = $false
try {
    $ownsMutex = $mutex.WaitOne(0)
    if (-not $ownsMutex) { exit 0 }
    [SignalMonitorMessageFilter]::Register()
    Add-Type -AssemblyName Microsoft.VisualBasic
    try { $workbook = [Microsoft.VisualBasic.Interaction]::GetObject($resolvedPath, $null) } catch { exit 0 }
    $excel = $workbook.Application
    $config = $workbook.Worksheets.Item("Config")
    $signalsSheet = $workbook.Worksheets.Item("Sinais")
    $historySheet = $workbook.Worksheets.Item("Historico_Sinais")
    $rawSheet = $workbook.Worksheets.Item("RTD_Profit")
    $signalsTable = $signalsSheet.ListObjects.Item("tblSinais")
    $historyTable = $historySheet.ListObjects.Item("tblHistoricoSinais")
    $signalMap = Get-TableMap $signalsTable
    $historyMap = Get-TableMap $historyTable
    $known = @{}
    $seen = @{}
    for ($index = $historyTable.ListRows.Count; $index -ge 1; $index--) {
        $candidateRow = $historyTable.ListRows.Item($index)
        if ([string]::IsNullOrWhiteSpace([string]$candidateRow.Range.Cells.Item(1, 1).Value2)) { $candidateRow.Delete() }
    }
    for ($index = 1; $index -le $historyTable.ListRows.Count; $index++) {
        $historyRow = $historyTable.ListRows.Item($index)
        $id = [string](Get-ListValue $historyRow $historyMap "signal_id")
        if (-not [string]::IsNullOrWhiteSpace($id)) {
            $known[$id] = $index
            $seen[$id] = @{
                High = [double](Get-ListValue $historyRow $historyMap "last_seen_high")
                Low = [double](Get-ListValue $historyRow $historyMap "last_seen_low")
            }
        }
    }

    Set-ExcelScalarValue $config.Range("I11") "ATIVO"
    Set-ExcelScalarValue $config.Range("I12") ([datetime]::Now)
    $config.Range("I12").NumberFormatLocal = "dd/mm/aaaa hh:mm:ss"
    $workbook.Save()

    while ($true) {
        try {
            if ([string]$config.Range("N11").Value2 -notmatch '^(?i)SIM$') { break }
            $signalsSheet.Calculate()
            $spot = [double]$config.Range("I3").Value2
            $dayHigh = [double]$config.Range("I5").Value2
            $dayLow = [double]$config.Range("I6").Value2
            if ($spot -le 0 -or $dayHigh -le 0 -or $dayLow -le 0) {
                Start-Sleep -Seconds ([Math]::Max(5, $IntervalSeconds))
                continue
            }
            $changed = $false
            for ($index = 1; $index -le $signalsTable.ListRows.Count; $index++) {
                $signalRow = $signalsTable.ListRows.Item($index)
                Set-SignalStateAppearance $signalRow $signalMap
                $state = [string](Get-ListValue $signalRow $signalMap "Estado")
                $id = [string](Get-ListValue $signalRow $signalMap "signal_id")
                if ($state -eq "ACIONADO" -and -not $known.ContainsKey($id)) {
                    $historyRow = Add-HistorySignal $historyTable $historyMap $signalRow $signalMap $dayHigh $dayLow
                    $known[$id] = $historyRow.Index
                    $seen[$id] = @{ High = $dayHigh; Low = $dayLow }
                    $changed = $true
                }
            }

            foreach ($id in @($known.Keys)) {
                $rowIndex = [int]$known[$id]
                if ($rowIndex -le 0 -or $rowIndex -gt $historyTable.ListRows.Count) { continue }
                $historyRow = $historyTable.ListRows.Item($rowIndex)
                $invalidatedAt = Get-ListValue $historyRow $historyMap "invalidated_at"
                $target3At = Get-ListValue $historyRow $historyMap "target_3_at"
                if ($null -ne $invalidatedAt -or $null -ne $target3At) { continue }
                if (-not $seen.ContainsKey($id)) { $seen[$id] = @{ High = $dayHigh; Low = $dayLow } }
                $lastHigh = [double]$seen[$id].High
                $lastLow = [double]$seen[$id].Low
                $newHigh = $dayHigh -gt $lastHigh + 0.000001
                $newLow = $dayLow -lt $lastLow - 0.000001
                $direction = [string](Get-ListValue $historyRow $historyMap "direction")
                $invalidation = [double](Get-ListValue $historyRow $historyMap "invalidation")
                $targetHits = @()
                for ($targetIndex = 1; $targetIndex -le 3; $targetIndex++) {
                    $target = Get-ListValue $historyRow $historyMap "target_$targetIndex"
                    $targetAt = Get-ListValue $historyRow $historyMap "target_${targetIndex}_at"
                    if ($null -eq $target -or $null -ne $targetAt) { continue }
                    $hit = if ($direction -eq "ALTA") { $newHigh -and $dayHigh -ge [double]$target } else { $newLow -and $dayLow -le [double]$target }
                    if ($hit) { $targetHits += $targetIndex }
                }
                $invalidHit = if ($direction -eq "ALTA") { $newLow -and $dayLow -le $invalidation } else { $newHigh -and $dayHigh -ge $invalidation }
                if ($targetHits.Count -gt 0 -or $invalidHit) {
                    $now = [datetime]::Now
                    foreach ($targetIndex in $targetHits) { Set-ListValue $historyRow $historyMap "target_${targetIndex}_at" $now }
                    if ($invalidHit) { Set-ListValue $historyRow $historyMap "invalidated_at" $now }
                    $firstOutcome = [string](Get-ListValue $historyRow $historyMap "first_outcome")
                    if ([string]::IsNullOrWhiteSpace($firstOutcome)) {
                        if ($invalidHit -and $targetHits.Count -gt 0) {
                            Set-ListValue $historyRow $historyMap "first_outcome" "AMBIGUO_60S"
                            Set-ListValue $historyRow $historyMap "ambiguity_flag" "ALVO E INVALIDACAO NO MESMO INTERVALO"
                        }
                        elseif ($invalidHit) { Set-ListValue $historyRow $historyMap "first_outcome" "INVALIDADO" }
                        else { Set-ListValue $historyRow $historyMap "first_outcome" "T$($targetHits | Measure-Object -Minimum | Select-Object -ExpandProperty Minimum)" }
                        Set-ListValue $historyRow $historyMap "first_outcome_at" $now
                        Set-ListValue $historyRow $historyMap "outcome_spot" $spot
                        $ticker = [string](Get-ListValue $historyRow $historyMap "ticker")
                        Set-ListValue $historyRow $historyMap "outcome_option_price" (Get-LiveOptionPrice $rawSheet $ticker)
                    }
                    Set-ListValue $historyRow $historyMap "last_seen_high" $dayHigh
                    Set-ListValue $historyRow $historyMap "last_seen_low" $dayLow
                    $changed = $true
                }
                $seen[$id] = @{ High = $dayHigh; Low = $dayLow }
            }
            Set-ExcelScalarValue $config.Range("I12") ([datetime]::Now)
            if ($changed) { $workbook.Save() }
            Start-Sleep -Seconds ([Math]::Max(5, $IntervalSeconds))
        }
        catch {
            $errorMessage = $_.Exception.Message
            Write-Output "Monitor interrompido: $errorMessage"
            try {
                Set-ExcelScalarValue $config.Range("I11") "ERRO"
                Set-ExcelScalarValue $config.Range("I12") ([datetime]::Now)
                $workbook.Save()
            }
            catch { }
            break
        }
    }
}
finally {
    try { [SignalMonitorMessageFilter]::Revoke() } catch { }
    if ($ownsMutex) { try { $mutex.ReleaseMutex() } catch { } }
    $mutex.Dispose()
}
