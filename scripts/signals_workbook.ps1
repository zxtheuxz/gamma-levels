function Convert-ToExcelComValue {
    param($Value)
    if ($null -eq $Value) { return $null }
    if ($Value -is [long] -or $Value -is [ulong] -or $Value -is [decimal]) { return [double]$Value }
    return $Value
}

function Set-ExcelFormulaValue {
    param($Range, [string]$Formula, [int]$Attempts = 8)
    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $Range.Formula = $Formula
            return
        }
        catch {
            $lastError = $_
            if ($attempt -lt $Attempts) { Start-Sleep -Milliseconds 250 }
        }
    }
    throw $lastError.Exception
}

function Set-ExcelRangeMatrix {
    param($Range, [object[,]]$Matrix)
    try {
        $Range.Value2 = $Matrix
        return
    }
    catch {
        $rowCount = $Matrix.GetLength(0)
        $columnCount = $Matrix.GetLength(1)
        for ($row = 0; $row -lt $rowCount; $row++) {
            $rowMatrix = [object[,]]::new(1, $columnCount)
            for ($column = 0; $column -lt $columnCount; $column++) {
                $rowMatrix[0, $column] = $Matrix[$row, $column]
            }
            $rowRange = $Range.Cells.Item($row + 1, 1).Resize(1, $columnCount)
            try {
                $rowRange.Value2 = $rowMatrix
            }
            catch {
                for ($column = 0; $column -lt $columnCount; $column++) {
                    $cell = $Range.Cells.Item($row + 1, $column + 1)
                    $cell.Value2 = $Matrix[$row, $column]
                }
            }
        }
    }
}

function Set-ExcelScalarValue {
    param($Range, $Value)
    $cell = $Range.Cells.Item(1, 1)
    $normalized = Convert-ToExcelComValue $Value
    if ($null -eq $normalized) {
        [void]$cell.ClearContents()
        return
    }
    try {
        $cell.Value2 = $normalized
    }
    catch {
        if ($normalized -is [double] -or $normalized -is [float] -or $normalized -is [int]) {
            $number = [Convert]::ToString($normalized, [Globalization.CultureInfo]::InvariantCulture)
            Set-ExcelFormulaValue $cell "=$number"
        }
        else {
            $cell.Value2 = [string]$normalized
        }
    }
}

function Ensure-SignalConfiguration {
    param($Workbook, $Sheet, [int]$Navy, [int]$Teal, [int]$White, [int]$Yellow, [int]$Green)

    $Sheet.Range("H1:J1").UnMerge()
    $Sheet.Range("H1:J1").Merge()
    $Sheet.Range("H1").Value2 = "SINAIS - RTD ATIVO"
    $Sheet.Range("H1:J1").Interior.Color = $Navy
    $Sheet.Range("H1:J1").Font.Color = $White
    $Sheet.Range("H1:J1").Font.Bold = $true
    $Sheet.Range("H1:J1").HorizontalAlignment = -4108

    $rtdLabels = @("Ultimo", "Abertura", "Maxima", "Minima", "Fech. anterior", "Volume", "Negocios", "Hora", "Status monitor", "Ultima leitura")
    for ($index = 0; $index -lt $rtdLabels.Count; $index++) {
        $row = 3 + $index
        $Sheet.Range("H$row").Value2 = $rtdLabels[$index]
        $Sheet.Range("H$row").Font.Bold = $true
    }
    Set-ExcelFormulaValue $Sheet.Range("I3") "=`$B`$4"
    $attributes = @("ABE", "MAX", "MIN", "FEC", "VOL", "NEG", "HOR")
    for ($index = 0; $index -lt $attributes.Count; $index++) {
        $row = 4 + $index
        $attribute = $attributes[$index]
        Set-ExcelFormulaValue $Sheet.Range("I$row") $('=IF($B$3="","",RTD("RTDTrading.RTDServer",,$B$3&"_B_0","' + $attribute + '"))')
    }
    if ([string]::IsNullOrWhiteSpace([string]$Sheet.Range("I11").Value2)) { $Sheet.Range("I11").Value2 = "AGUARDANDO" }
    $Sheet.Range("I3:I7").NumberFormatLocal = "0,00"
    $Sheet.Range("I8:I9").NumberFormatLocal = "#.##0"
    $Sheet.Range("I10").NumberFormatLocal = "hh:mm:ss"
    $Sheet.Range("I3:I10").Interior.Color = $Green
    $Sheet.Range("H3:I12").Borders.LineStyle = 1

    $Sheet.Range("L1:N1").UnMerge()
    $Sheet.Range("L1:N1").Merge()
    $Sheet.Range("L1").Value2 = "PARAMETROS DE SINAIS"
    $Sheet.Range("L1:N1").Interior.Color = $Navy
    $Sheet.Range("L1:N1").Font.Color = $White
    $Sheet.Range("L1:N1").Font.Bold = $true
    $Sheet.Range("L1:N1").HorizontalAlignment = -4108

    $labels = @(
        "Forca minima", "RR minimo", "Horizonte (pregoes)", "Delta minimo", "Delta maximo",
        "Choque de IV", "Buffer do passo", "Intervalo monitor (s)", "Monitor habilitado",
        "Ticker CALL manual", "Ticker PUT manual"
    )
    $defaults = @(65.0, 1.5, 5, 0.50, 0.70, 0.03, 0.25, 60, "SIM", "", "")
    $names = @(
        "sig_strength_min", "sig_rr_min", "sig_horizon_days", "sig_delta_min", "sig_delta_max",
        "sig_iv_shock", "sig_buffer_step", "sig_monitor_interval", "sig_monitor_enabled",
        "sig_call_override", "sig_put_override"
    )
    for ($index = 0; $index -lt $labels.Count; $index++) {
        $row = 3 + $index
        $parameterCell = $Sheet.Range("N$row")
        $currentValue = $parameterCell.Value2
        $useDefault = $null -eq $currentValue -or ($index -lt 9 -and [string]::IsNullOrWhiteSpace([string]$currentValue))
        if ($useDefault) { $parameterCell.Value2 = $defaults[$index] }
    }
    for ($index = 0; $index -lt $labels.Count; $index++) {
        $row = 3 + $index
        $Sheet.Range("L$row:M$row").UnMerge()
        $Sheet.Range("L$row:M$row").Merge()
        $Sheet.Range("L$row").Value2 = $labels[$index]
        $Sheet.Range("L$row").Font.Bold = $true
        $Sheet.Range("N$row").Interior.Color = $Yellow
        $Sheet.Range("N$row").Font.Color = 16711680
        try { $Workbook.Names.Item($names[$index]).Delete() } catch { }
        [void]$Workbook.Names.Add($names[$index], "='Config'!`$N`$$row")
    }
    $Sheet.Range("N3:N4").NumberFormatLocal = "0,00"
    $Sheet.Range("N5").NumberFormatLocal = "0"
    $Sheet.Range("N6:N9").NumberFormatLocal = "0,00"
    $Sheet.Range("N10").NumberFormatLocal = "0"
    $Sheet.Range("L3:N13").Borders.LineStyle = 1
    $Sheet.Columns.Item("H").ColumnWidth = 18
    $Sheet.Columns.Item("I").ColumnWidth = 22
    $Sheet.Columns.Item("J").ColumnWidth = 3
    $Sheet.Range("L:M").ColumnWidth = 15
    $Sheet.Columns.Item("N").ColumnWidth = 18
    $Sheet.Range("H15:N15").Merge()
    $Sheet.Range("H15").Value2 = "Fonte RTD: https://ajuda.nelogica.com.br/hc/pt-br/articles/7834206674075-Significados-e-sintaxe-do-RTD"
    $Sheet.Range("H15:N15").Font.Size = 8
    $Sheet.Range("H15:N15").WrapText = $true

    return [pscustomobject]@{
        StrengthMin = [double]$Sheet.Range("N3").Value2
        RrMin = [double]$Sheet.Range("N4").Value2
        HorizonDays = [int]$Sheet.Range("N5").Value2
        DeltaMin = [double]$Sheet.Range("N6").Value2
        DeltaMax = [double]$Sheet.Range("N7").Value2
        IvShock = [double]$Sheet.Range("N8").Value2
        BufferStep = [double]$Sheet.Range("N9").Value2
        MonitorInterval = [int]$Sheet.Range("N10").Value2
        MonitorEnabled = [string]$Sheet.Range("N11").Value2
        CallOverride = ([string]$Sheet.Range("N12").Value2).Trim()
        PutOverride = ([string]$Sheet.Range("N13").Value2).Trim()
    }
}

function Get-PayloadField {
    param([object[]]$Columns, [object[]]$Row, [string]$Name)
    $index = [Array]::IndexOf($Columns, $Name)
    if ($index -lt 0) { return $null }
    return $Row[$index]
}

function Ensure-SignalHistorySheet {
    param($Workbook, [int]$Navy, [int]$White)
    $sheet = $null
    for ($index = 1; $index -le $Workbook.Worksheets.Count; $index++) {
        if ($Workbook.Worksheets.Item($index).Name -eq "Historico_Sinais") { $sheet = $Workbook.Worksheets.Item($index); break }
    }
    if ($null -eq $sheet) {
        $missing = [System.Reflection.Missing]::Value
        $sheet = $Workbook.Worksheets.Add($missing, $Workbook.Worksheets.Item($Workbook.Worksheets.Count), 1, $missing)
        $sheet.Name = "Historico_Sinais"
    }
    if ([string]::IsNullOrWhiteSpace([string]$sheet.Range("A1").Value2)) {
        $headers = @(
            "signal_id", "session_date", "activated_at", "direction", "setup", "level", "zone_low", "zone_high",
            "strength", "trigger", "invalidation", "target_1", "target_2", "target_3", "target_1_asset_pct",
            "target_2_asset_pct", "target_3_asset_pct", "ticker", "option_entry_price", "option_price_source",
            "option_iv_source", "option_proj_1_low", "option_proj_1_base", "option_proj_1_high", "option_proj_2_low",
            "option_proj_2_base", "option_proj_2_high", "option_proj_3_low", "option_proj_3_base", "option_proj_3_high",
            "target_1_at", "target_2_at", "target_3_at", "invalidated_at", "first_outcome", "first_outcome_at",
            "outcome_spot", "outcome_option_price", "activation_day_high", "activation_day_low", "last_seen_high",
            "last_seen_low", "ambiguity_flag", "data_quality"
        )
        $range = $sheet.Range("A1").Resize(1, $headers.Count)
        for ($column = 0; $column -lt $headers.Count; $column++) {
            $headerCell = $sheet.Cells.Item(1, $column + 1)
            $headerCell.Value2 = [string]$headers[$column]
        }
        $range.Interior.Color = $Navy
        $range.Font.Color = $White
        $range.Font.Bold = $true
        $table = $sheet.ListObjects.Add(1, $range, $null, 1)
        $table.Name = "tblHistoricoSinais"
        $table.TableStyle = "TableStyleMedium2"
        $sheet.Rows.Item(1).RowHeight = 24
        $sheet.Columns.ColumnWidth = 14
        $sheet.Columns.Item("A").ColumnWidth = 34
        $sheet.Columns.Item("C").ColumnWidth = 21
        $sheet.Columns.Item("E").ColumnWidth = 20
        $sheet.Cells.Font.Name = "Aptos"
        $sheet.Cells.Font.Size = 9
    }
    $historyTable = $sheet.ListObjects.Item("tblHistoricoSinais")
    for ($rowIndex = $historyTable.ListRows.Count; $rowIndex -ge 1; $rowIndex--) {
        $historyRow = $historyTable.ListRows.Item($rowIndex)
        if ([string]::IsNullOrWhiteSpace([string]$historyRow.Range.Cells.Item(1, 1).Value2)) {
            $historyRow.Delete()
        }
    }
    return $sheet
}

function Build-SignalsSheet {
    param(
        $Sheet, $Payload, $ConfigSheet,
        [int]$Navy, [int]$Teal, [int]$White, [int]$Gray, [int]$LightBlue,
        [int]$LightGreen, [int]$LightAmber, [int]$LightRed, [int]$Green, [int]$Amber, [int]$Red
    )
    $sourceColumns = @($Payload.signals.columns)
    $sourceRows = @($Payload.signals.rows)
    $headers = @(
        "Prioridade", "signal_id", "Direcao", "Setup", "Estado", "Forca", "Classe", "Nivel", "Zona Inf", "Zona Sup",
        "Gatilho", "Invalidacao", "T1", "T1 Fonte", "Ativo T1 %", "RR T1", "Opcao T1 Baixa %", "Opcao T1 Base %",
        "Opcao T1 Alta %", "T2", "T2 Fonte", "Ativo T2 %", "RR T2", "Opcao T2 Baixa %", "Opcao T2 Base %",
        "Opcao T2 Alta %", "T3", "T3 Fonte", "Ativo T3 %", "RR T3", "Opcao T3 Baixa %", "Opcao T3 Base %",
        "Opcao T3 Alta %", "Ticker Usado", "Selecao", "Preco Opcao", "Delta", "DTE", "IV Fonte", "Estado Base", "Buffer"
    )
    $fieldMap = @(
        $null, "signal_id", "direction", "setup", $null, "strength", "strength_label", "level", "zone_low", "zone_high",
        "trigger", "invalidation", "target_1", "target_1_source", "target_1_asset_pct", "target_1_rr",
        "target_1_option_low_pct", "target_1_option_base_pct", "target_1_option_high_pct",
        "target_2", "target_2_source", "target_2_asset_pct", "target_2_rr", "target_2_option_low_pct",
        "target_2_option_base_pct", "target_2_option_high_pct", "target_3", "target_3_source", "target_3_asset_pct",
        "target_3_rr", "target_3_option_low_pct", "target_3_option_base_pct", "target_3_option_high_pct",
        "selected_ticker", "option_selection_flag", "option_market_price", "option_delta", "option_dte", "option_iv_source",
        "initial_state", "buffer"
    )

    $Sheet.Cells.Font.Name = "Aptos"
    $Sheet.Cells.Font.Size = 9
    $Sheet.Range("A1:O1").Merge()
    $Sheet.Range("A1").Value2 = "SINAIS OPERACIONAIS - $([string]$ConfigSheet.Range('B3').Value2)"
    $Sheet.Range("A1:O1").Interior.Color = $Navy
    $Sheet.Range("A1:O1").Font.Color = $White
    $Sheet.Range("A1:O1").Font.Bold = $true
    $Sheet.Range("A1:O1").Font.Size = 16
    $Sheet.Range("A1:O1").HorizontalAlignment = -4108
    $Sheet.Range("A2:O2").Merge()
    $Sheet.Range("A2").Value2 = "Forca minima $($Payload.signal_config.strength_min)/100 | RR minimo $($Payload.signal_config.reward_risk_min) | Horizonte $($Payload.signal_config.horizon_days) pregoes | Monitor $($Payload.signal_config.monitor_interval_seconds)s"
    $Sheet.Range("A2:O2").Font.Color = 5855577
    $Sheet.Range("A2:O2").HorizontalAlignment = -4108

    $headerRow = 17
    $dataFirstRow = 18
    $matrix = [object[,]]::new($sourceRows.Count + 1, $headers.Count)
    for ($column = 0; $column -lt $headers.Count; $column++) { $matrix[0, $column] = $headers[$column] }
    for ($rowIndex = 0; $rowIndex -lt $sourceRows.Count; $rowIndex++) {
        $rowValues = @($sourceRows[$rowIndex])
        for ($column = 0; $column -lt $headers.Count; $column++) {
            if ($column -eq 0) { $matrix[($rowIndex + 1), $column] = $rowIndex + 1; continue }
            if ($column -eq 4) { continue }
            $matrix[($rowIndex + 1), $column] = Convert-ToExcelComValue (Get-PayloadField $sourceColumns $rowValues $fieldMap[$column])
        }
    }
    $tableRange = $Sheet.Range("A$headerRow").Resize($sourceRows.Count + 1, $headers.Count)
    Set-ExcelRangeMatrix $tableRange $matrix
    $Sheet.Range("A$headerRow").Resize(1, $headers.Count).Interior.Color = $Navy
    $Sheet.Range("A$headerRow").Resize(1, $headers.Count).Font.Color = $White
    $Sheet.Range("A$headerRow").Resize(1, $headers.Count).Font.Bold = $true
    if ($sourceRows.Count -gt 0) {
        $table = $Sheet.ListObjects.Add(1, $tableRange, $null, 1)
        $table.Name = "tblSinais"
        $table.TableStyle = "TableStyleMedium2"
    }

    for ($rowIndex = 0; $rowIndex -lt $sourceRows.Count; $rowIndex++) {
        $row = $dataFirstRow + $rowIndex
        $formula = '=IF(''Config''!$I$3="","SEM RTD",IF($AN' + $row + '<>"OBSERVAR",$AN' + $row + ',IF($D' + $row + '="CALL_REVERSAO",IF(''Config''!$I$3<$L' + $row + ',"INVALIDADO",IF(AND(''Config''!$I$6<=$J' + $row + ',''Config''!$I$3>=$K' + $row + '),"ACIONADO",IF(OR(''Config''!$I$6<=$J' + $row + ',ABS(''Config''!$I$3-$H' + $row + ')<=($J' + $row + '-$I' + $row + ')),"ARMADO","OBSERVAR"))),IF($D' + $row + '="CALL_ROMPIMENTO",IF(AND(''Config''!$I$3>=$K' + $row + ',OR(''Config''!$I$4<=$J' + $row + ',''Config''!$I$6<=$J' + $row + ')),"ACIONADO",IF(AND(''Config''!$I$4>$K' + $row + ',''Config''!$I$6>$J' + $row + '),"AGUARDAR RETESTE",IF(ABS(''Config''!$I$3-$H' + $row + ')<=($J' + $row + '-$I' + $row + '),"ARMADO","OBSERVAR"))),IF($D' + $row + '="PUT_REVERSAO",IF(''Config''!$I$3>$L' + $row + ',"INVALIDADO",IF(AND(''Config''!$I$5>=$I' + $row + ',''Config''!$I$3<=$K' + $row + '),"ACIONADO",IF(OR(''Config''!$I$5>=$I' + $row + ',ABS(''Config''!$I$3-$H' + $row + ')<=($J' + $row + '-$I' + $row + ')),"ARMADO","OBSERVAR"))),IF(AND(''Config''!$I$3<=$K' + $row + ',OR(''Config''!$I$4>=$I' + $row + ',''Config''!$I$5>=$I' + $row + ')),"ACIONADO",IF(AND(''Config''!$I$4<$K' + $row + ',''Config''!$I$5<$I' + $row + '),"AGUARDAR RETESTE",IF(ABS(''Config''!$I$3-$H' + $row + ')<=($J' + $row + '-$I' + $row + '),"ARMADO","OBSERVAR")))))))'
        $rowValues = @($sourceRows[$rowIndex])
        $setup = [string](Get-PayloadField $sourceColumns $rowValues "setup")
        $prefix = '=IF(''Config''!$I$3="","SEM RTD",IF($AN' + $row + '<>"OBSERVAR",$AN' + $row + ','
        $body = switch ($setup) {
            "CALL_REVERSAO" { 'IF(''Config''!$I$3<$L' + $row + ',"INVALIDADO",IF(AND(''Config''!$I$6<=$J' + $row + ',''Config''!$I$3>=$K' + $row + '),"ACIONADO",IF(OR(''Config''!$I$6<=$J' + $row + ',ABS(''Config''!$I$3-$H' + $row + ')<=($J' + $row + '-$I' + $row + ')),"ARMADO","OBSERVAR")))' }
            "CALL_ROMPIMENTO" { 'IF(AND(''Config''!$I$3>=$K' + $row + ',OR(''Config''!$I$4<=$J' + $row + ',''Config''!$I$6<=$J' + $row + ')),"ACIONADO",IF(AND(''Config''!$I$4>$K' + $row + ',''Config''!$I$6>$J' + $row + '),"AGUARDAR RETESTE",IF(ABS(''Config''!$I$3-$H' + $row + ')<=($J' + $row + '-$I' + $row + '),"ARMADO","OBSERVAR")))' }
            "PUT_REVERSAO" { 'IF(''Config''!$I$3>$L' + $row + ',"INVALIDADO",IF(AND(''Config''!$I$5>=$I' + $row + ',''Config''!$I$3<=$K' + $row + '),"ACIONADO",IF(OR(''Config''!$I$5>=$I' + $row + ',ABS(''Config''!$I$3-$H' + $row + ')<=($J' + $row + '-$I' + $row + ')),"ARMADO","OBSERVAR")))' }
            default { 'IF(AND(''Config''!$I$3<=$K' + $row + ',OR(''Config''!$I$4>=$I' + $row + ',''Config''!$I$5>=$I' + $row + ')),"ACIONADO",IF(AND(''Config''!$I$4<$K' + $row + ',''Config''!$I$5<$I' + $row + '),"AGUARDAR RETESTE",IF(ABS(''Config''!$I$3-$H' + $row + ')<=($J' + $row + '-$I' + $row + '),"ARMADO","OBSERVAR")))' }
        }
        $formula = $prefix + $body + '))'
        $stateCell = $Sheet.Range("E$row")
        Set-ExcelFormulaValue $stateCell $formula
    }

    $eligible = @()
    for ($index = 0; $index -lt $sourceRows.Count; $index++) {
        $values = @($sourceRows[$index])
        if ((Get-PayloadField $sourceColumns $values "initial_state") -eq "OBSERVAR") {
            $eligible += [pscustomobject]@{ Index = $index; Direction = Get-PayloadField $sourceColumns $values "direction"; Strength = [double](Get-PayloadField $sourceColumns $values "strength") }
        }
    }
    foreach ($card in @(@("ALTA", "A", "G"), @("BAIXA", "I", "O"))) {
        $direction = $card[0]; $left = $card[1]; $right = $card[2]
        $selected = $eligible | Where-Object { $_.Direction -eq $direction } | Sort-Object Strength -Descending | Select-Object -First 1
        $Sheet.Range("${left}4:${right}4").Merge()
        $Sheet.Range("$left`4").Value2 = "MELHOR SINAL DE $direction"
        $Sheet.Range("${left}4:${right}4").Interior.Color = $Teal
        $Sheet.Range("${left}4:${right}4").Font.Color = $White
        $Sheet.Range("${left}4:${right}4").Font.Bold = $true
        if ($null -eq $selected) {
            $Sheet.Range("${left}5:${right}14").Merge()
            $Sheet.Range("$left`5").Value2 = "Nenhum sinal elegivel no momento"
            continue
        }
        $sourceRow = $dataFirstRow + $selected.Index
        $labels = @("Estado", "Setup", "Zona", "Forca", "Gatilho", "Invalidacao", "Alvo 1", "Alvo 2", "Alvo 3", "Opcao")
        $formulas = @(
            ("=E$sourceRow")
            ("=D$sourceRow")
            ('=TEXT(I' + $sourceRow + ',"0,00")&" - "&TEXT(J' + $sourceRow + ',"0,00")')
            ('=TEXT(F' + $sourceRow + ',"0,0")&"/100 - "&G' + $sourceRow)
            ("=K$sourceRow")
            ("=L$sourceRow")
            ('=IF(M' + $sourceRow + '="","n/d",TEXT(M' + $sourceRow + ',"0,00")&" | Ativo "&TEXT(O' + $sourceRow + ',"0,00%")&" | Opcao "&TEXT(R' + $sourceRow + ',"0,0%")&" ["&TEXT(Q' + $sourceRow + ',"0,0%")&" a "&TEXT(S' + $sourceRow + ',"0,0%")&"]")')
            ('=IF(T' + $sourceRow + '="","n/d",TEXT(T' + $sourceRow + ',"0,00")&" | Ativo "&TEXT(V' + $sourceRow + ',"0,00%")&" | Opcao "&TEXT(Y' + $sourceRow + ',"0,0%")&" ["&TEXT(X' + $sourceRow + ',"0,0%")&" a "&TEXT(Z' + $sourceRow + ',"0,0%")&"]")')
            ('=IF(AA' + $sourceRow + '="","n/d",TEXT(AA' + $sourceRow + ',"0,00")&" | Ativo "&TEXT(AC' + $sourceRow + ',"0,00%")&" | Opcao "&TEXT(AF' + $sourceRow + ',"0,0%")&" ["&TEXT(AE' + $sourceRow + ',"0,0%")&" a "&TEXT(AG' + $sourceRow + ',"0,0%")&"]")')
            ('=AH' + $sourceRow + '&" | Delta "&TEXT(AK' + $sourceRow + ',"0,00")&" | DTE "&TEXT(AL' + $sourceRow + ',"0")')
        )
        for ($index = 0; $index -lt $labels.Count; $index++) {
            $row = 5 + $index
            $labelEnd = if ($left -eq "A") { "B" } else { "J" }
            $valueStart = if ($left -eq "A") { "C" } else { "K" }
            $Sheet.Range("${left}${row}:${labelEnd}${row}").Merge()
            $Sheet.Range("${valueStart}${row}:${right}${row}").Merge()
            $Sheet.Range("${valueStart}${row}:${right}${row}").HorizontalAlignment = -4131
            $Sheet.Range("$left$row").Value2 = $labels[$index]
            $cardValueCell = $Sheet.Range("$valueStart$row")
            Set-ExcelFormulaValue $cardValueCell $formulas[$index]
            $Sheet.Range("${left}${row}:${labelEnd}${row}").Interior.Color = $Gray
        }
    }

    if ($sourceRows.Count -gt 0) {
        $lastRow = $dataFirstRow + $sourceRows.Count - 1
        $Sheet.Range("F$dataFirstRow:F$lastRow").NumberFormatLocal = "0,0"
        $Sheet.Range("H$dataFirstRow:M$lastRow").NumberFormatLocal = "0,00"
        foreach ($column in @("O", "Q", "R", "S", "V", "X", "Y", "Z", "AC", "AE", "AF", "AG")) {
            $Sheet.Range("${column}${dataFirstRow}:${column}${lastRow}").NumberFormatLocal = "0,00%"
        }
        foreach ($column in @("P", "W", "AD")) { $Sheet.Range("${column}${dataFirstRow}:${column}${lastRow}").NumberFormatLocal = "0,00" }
        $Sheet.Range("AJ$dataFirstRow:AK$lastRow").NumberFormatLocal = "0,00"
        $Sheet.Range("AL$dataFirstRow:AL$lastRow").NumberFormatLocal = "0"
        $stateRange = $Sheet.Range("E$dataFirstRow:E$lastRow")
        $stateRange.FormatConditions.Delete()
        $conditions = @(
            [pscustomobject]@{ Formula = ('=$E' + $dataFirstRow + '="ACIONADO"'); Fill = $LightGreen; Font = $Green }
            [pscustomobject]@{ Formula = ('=$E' + $dataFirstRow + '="ARMADO"'); Fill = $LightAmber; Font = $Amber }
            [pscustomobject]@{ Formula = ('=OR($E' + $dataFirstRow + '="INVALIDADO",$E' + $dataFirstRow + '="SEM ESPACO",$E' + $dataFirstRow + '="SEM OPCAO")'); Fill = $LightRed; Font = $Red }
        )
        foreach ($condition in $conditions) {
            try {
                $format = $stateRange.FormatConditions.Add(2, 3, $condition.Formula)
                $format.Interior.Color = $condition.Fill
                $format.Font.Color = $condition.Font
                $format.Font.Bold = $true
            }
            catch { }
        }
    }
    $Sheet.Range("A16:O16").Merge()
    $Sheet.Range("A16").Value2 = "RANKING COMPLETO - estados reagem ao RTD; forca, niveis e projecoes atualizam no clique"
    $Sheet.Range("A16:O16").Interior.Color = $Teal
    $Sheet.Range("A16:O16").Font.Color = $White
    $Sheet.Range("A16:O16").Font.Bold = $true
    $Sheet.Range("A:AO").ColumnWidth = 13
    $Sheet.Columns.Item("B").ColumnWidth = 29
    $Sheet.Columns.Item("D").ColumnWidth = 20
    $Sheet.Columns.Item("E").ColumnWidth = 18
    $Sheet.Columns.Item("G").ColumnWidth = 15
    $Sheet.Columns.Item("N").ColumnWidth = 20
    $Sheet.Columns.Item("U").ColumnWidth = 20
    $Sheet.Columns.Item("AB").ColumnWidth = 20
    $Sheet.Columns.Item("AH").ColumnWidth = 18
    $Sheet.Columns.Item("AI").ColumnWidth = 18
    $Sheet.Columns.Item("AN").ColumnWidth = 20
    $Sheet.Rows.Item(1).RowHeight = 28
    $Sheet.Rows.Item(17).RowHeight = 30
    $Sheet.Activate()
    $Sheet.Application.ActiveWindow.DisplayGridlines = $false
    $Sheet.Application.ActiveWindow.SplitRow = 17
    $Sheet.Application.ActiveWindow.SplitColumn = 5
    $Sheet.Application.ActiveWindow.FreezePanes = $true
    $Sheet.Application.ActiveWindow.Zoom = 80
    $Sheet.Range("A1").Select() | Out-Null
}
