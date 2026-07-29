param(
    [string]$OutputPath = "E:\gamma levels\profit_rtd.xlsx"
)

$ErrorActionPreference = "Stop"

function Get-ExcelColor([int]$Red, [int]$Green, [int]$Blue) {
    return $Red + (256 * $Green) + (65536 * $Blue)
}

if (Test-Path -LiteralPath $OutputPath) {
    throw "O arquivo já existe e não será sobrescrito: $OutputPath"
}

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $true
$excel.DisplayAlerts = $false
$workbook = $excel.Workbooks.Add()

try {
    while ($workbook.Worksheets.Count -lt 3) {
        [void]$workbook.Worksheets.Add()
    }

    $chain = $workbook.Worksheets.Item(1)
    $chain.Name = "Cadeia"
    $raw = $workbook.Worksheets.Item(2)
    $raw.Name = "RTD_Profit"
    $config = $workbook.Worksheets.Item(3)
    $config.Name = "Config"

    while ($workbook.Worksheets.Count -gt 3) {
        $workbook.Worksheets.Item($workbook.Worksheets.Count).Delete()
    }

    $navy = Get-ExcelColor 28 49 79
    $teal = Get-ExcelColor 0 120 140
    $lightBlue = Get-ExcelColor 221 235 247
    $lightYellow = Get-ExcelColor 255 242 204
    $lightGreen = Get-ExcelColor 226 239 218
    $white = Get-ExcelColor 255 255 255
    $gray = Get-ExcelColor 242 242 242
    $red = Get-ExcelColor 192 0 0

    # Configuração e instruções
    $config.Range("A1:F1").Merge()
    $config.Range("A1").Value2 = "GAMMA LEVELS — INTEGRAÇÃO PROFIT RTD"
    $config.Range("A1:F1").Interior.Color = $navy
    $config.Range("A1:F1").Font.Color = $white
    $config.Range("A1:F1").Font.Bold = $true
    $config.Range("A1:F1").Font.Size = 16
    $config.Range("A1:F1").HorizontalAlignment = -4108
    $config.Rows.Item(1).RowHeight = 28

    $config.Range("A3").Value2 = "Ativo-objeto"
    $config.Range("A4").Value2 = "Preço do ativo (RTD)"
    $config.Range("A5").Value2 = "Taxa anual"
    $config.Range("A6").Value2 = "Dividend yield"
    $config.Range("A7").Value2 = "Multiplicador"
    $config.Range("A8").Value2 = "Data-base"
    $config.Range("A9").Value2 = "Linhas disponíveis"
    $config.Range("A3:A9").Font.Bold = $true
    $config.Range("B3").Value2 = ""
    $config.Range("B4").FormulaR1C1 = '=IF(R[-1]C="","",RTD("RTDTrading.RTDServer",,R[-1]C&"_B_0","ULT"))'
    $config.Range("B5").Value2 = 0.15
    $config.Range("B6").Value2 = 0.0
    $config.Range("B7").Value2 = 100
    $config.Range("B8").Formula = "=TODAY()"
    $config.Range("B9").Value2 = 300
    $config.Range("B3").Interior.Color = $lightYellow
    $config.Range("B5:B7").Interior.Color = $lightYellow
    $config.Range("B4").Interior.Color = $lightGreen
    $config.Range("B5:B6").NumberFormatLocal = "0,00%"
    $config.Range("B4").NumberFormatLocal = "0,00"
    $config.Range("B7:B9").NumberFormatLocal = "#.##0"
    $config.Range("B8").NumberFormatLocal = "aaaa-mm-dd"
    $config.Range("A3:B9").Borders.LineStyle = 1

    $config.Range("A12:F12").Merge()
    $config.Range("A12").Value2 = "COMO USAR"
    $config.Range("A12:F12").Interior.Color = $teal
    $config.Range("A12:F12").Font.Color = $white
    $config.Range("A12:F12").Font.Bold = $true
    $instructions = @(
        "1. Digite o ticker do ativo-objeto em B3, por exemplo PETR4.",
        "2. Abra Opções > Grade de Opções no Profit e copie os códigos desejados.",
        "3. Cole somente os códigos na coluna A da aba RTD_Profit, a partir de A2.",
        "4. Mantenha o Profit e esta planilha abertos; os dados RTD atualizam automaticamente.",
        "5. Salve a planilha antes de executar a análise Python.",
        "6. Use calls e puts de pelo menos 2 ou 3 vencimentos e strikes além do ATM."
    )
    for ($index = 0; $index -lt $instructions.Count; $index++) {
        $config.Cells.Item(13 + $index, 1).Value2 = $instructions[$index]
        $config.Range("A$($index + 13):F$($index + 13)").Merge($false)
    }
    $config.Range("A13:F18").WrapText = $true
    $config.Range("A13:F18").RowHeight = 24

    $config.Range("A21").Value2 = "Fonte RTD"
    $config.Range("B21:F21").Merge()
    $config.Range("B21").Value2 = "https://ajuda.nelogica.com.br/hc/pt-br/articles/7834206674075-Significados-e-sintaxe-do-RTD"
    $config.Range("A22").Value2 = "Configuração"
    $config.Range("B22:F22").Merge()
    $config.Range("B22").Value2 = "https://ajuda.nelogica.com.br/hc/pt-br/articles/360044293432-Como-configurar-RTD-DDE-no-Profit"
    $config.Range("A21:A22").Font.Bold = $true
    $config.Range("B21:F22").Font.Size = 9
    $config.Range("B21:F22").WrapText = $true
    $config.Rows.Item(21).RowHeight = 28
    $config.Rows.Item(22).RowHeight = 28
    $config.Columns.Item("A").ColumnWidth = 24
    $config.Columns.Item("B").ColumnWidth = 20
    $config.Range("C:F").ColumnWidth = 15

    # Dados brutos RTD
    $rawHeaders = @(
        "ticker", "ultimo", "bid", "ask", "quantidade", "volume_financeiro",
        "open_interest", "strike", "vencimento", "iv", "iv_ask", "iv_bid",
        "delta_profit", "gamma_profit", "vega_profit", "hora"
    )
    for ($column = 0; $column -lt $rawHeaders.Count; $column++) {
        $raw.Cells.Item(1, $column + 1).Value2 = $rawHeaders[$column]
    }
    $raw.Range("A1:P1").Interior.Color = $navy
    $raw.Range("A1:P1").Font.Color = $white
    $raw.Range("A1:P1").Font.Bold = $true
    $raw.Range("A1:P1").HorizontalAlignment = -4108
    $raw.Range("A2:A301").Interior.Color = $lightYellow

    $rtdAttributes = @("ULT", "OCP", "OVD", "QTT", "VOL", "CAB", "PEX", "VEN", "IMPVT", "VIA", "VIB", "DELTA", "GAMA", "VEGA", "HOR")
    for ($offset = 0; $offset -lt $rtdAttributes.Count; $offset++) {
        $targetColumn = 2 + $offset
        $attribute = $rtdAttributes[$offset]
        $formula = '=IF(RC1="","",RTD("RTDTrading.RTDServer",,RC1&"_B_0","' + $attribute + '"))'
        $raw.Range($raw.Cells.Item(2, $targetColumn), $raw.Cells.Item(301, $targetColumn)).FormulaR1C1 = $formula
    }
    $raw.Range("B2:D301").NumberFormatLocal = "0,00"
    $raw.Range("E2:G301").NumberFormatLocal = "#.##0"
    $raw.Range("H2:H301").NumberFormatLocal = "0,00"
    $raw.Range("I2:I301").NumberFormatLocal = "aaaa-mm-dd"
    $raw.Range("J2:O301").NumberFormatLocal = "0,0000"
    $raw.Range("P2:P301").NumberFormatLocal = "hh:mm:ss"
    $raw.Range("A1:P301").AutoFilter() | Out-Null
    $raw.Columns.Item("A").ColumnWidth = 16
    $raw.Range("B:D").ColumnWidth = 12
    $raw.Columns.Item("E").ColumnWidth = 14
    $raw.Columns.Item("F").ColumnWidth = 20
    $raw.Columns.Item("G").ColumnWidth = 18
    $raw.Columns.Item("H").ColumnWidth = 12
    $raw.Columns.Item("I").ColumnWidth = 16
    $raw.Range("J:L").ColumnWidth = 12
    $raw.Range("M:O").ColumnWidth = 14
    $raw.Columns.Item("P").ColumnWidth = 12
    $raw.Activate()
    $excel.ActiveWindow.SplitRow = 1
    $excel.ActiveWindow.FreezePanes = $true

    # Cadeia normalizada para o Python. Gregas do Profit são mantidas apenas para comparação.
    $chainHeaders = @(
        "ticker", "option_type", "strike", "expiration", "open_interest", "volume",
        "implied_volatility", "underlying_price", "multiplier", "option_price",
        "interest_rate", "dividend_yield", "delta_profit", "gamma_profit", "vega_profit",
        "bid", "ask", "update_time"
    )
    for ($column = 0; $column -lt $chainHeaders.Count; $column++) {
        $chain.Cells.Item(1, $column + 1).Value2 = $chainHeaders[$column]
    }
    $chain.Range("A1:R1").Interior.Color = $navy
    $chain.Range("A1:R1").Font.Color = $white
    $chain.Range("A1:R1").Font.Bold = $true

    $chainFormulas = @(
        '=IF(''RTD_Profit''!RC1="","",''RTD_Profit''!RC1)',
        '=IF(RC1="","",IF(ISNUMBER(SEARCH(MID(RC1,5,1),"ABCDEFGHIJKL")),"call","put"))',
        '=IF(RC1="","",''RTD_Profit''!RC8)',
        '=IF(RC1="","",''RTD_Profit''!RC9)',
        '=IF(RC1="","",''RTD_Profit''!RC7)',
        '=IF(RC1="","",''RTD_Profit''!RC5)',
        '=IF(RC1="","",IF(AND(ISNUMBER(''RTD_Profit''!RC11),ISNUMBER(''RTD_Profit''!RC12)),AVERAGE(''RTD_Profit''!RC11,''RTD_Profit''!RC12),''RTD_Profit''!RC10))',
        '=IF(RC1="","",Config!R4C2)',
        '=IF(RC1="","",Config!R7C2)',
        '=IF(RC1="","",IF(AND(ISNUMBER(''RTD_Profit''!RC3),ISNUMBER(''RTD_Profit''!RC4),''RTD_Profit''!RC3>0,''RTD_Profit''!RC4>0),AVERAGE(''RTD_Profit''!RC3,''RTD_Profit''!RC4),''RTD_Profit''!RC2))',
        '=IF(RC1="","",Config!R5C2)',
        '=IF(RC1="","",Config!R6C2)',
        '=IF(RC1="","",''RTD_Profit''!RC13)',
        '=IF(RC1="","",''RTD_Profit''!RC14)',
        '=IF(RC1="","",''RTD_Profit''!RC15)',
        '=IF(RC1="","",''RTD_Profit''!RC3)',
        '=IF(RC1="","",''RTD_Profit''!RC4)',
        '=IF(RC1="","",''RTD_Profit''!RC16)'
    )
    for ($column = 0; $column -lt $chainFormulas.Count; $column++) {
        $targetColumn = $column + 1
        $chain.Range($chain.Cells.Item(2, $targetColumn), $chain.Cells.Item(301, $targetColumn)).FormulaR1C1 = $chainFormulas[$column]
    }
    $chain.Range("C2:C301").NumberFormatLocal = "0,00"
    $chain.Range("H2:J301").NumberFormatLocal = "0,00"
    $chain.Range("P2:Q301").NumberFormatLocal = "0,00"
    $chain.Range("D2:D301").NumberFormatLocal = "aaaa-mm-dd"
    $chain.Range("E2:F301").NumberFormatLocal = "#.##0"
    $chain.Range("G2:G301").NumberFormatLocal = "0,0000"
    $chain.Range("K2:O301").NumberFormatLocal = "0,0000"
    $chain.Range("R2:R301").NumberFormatLocal = "hh:mm:ss"
    $chain.Range("A1:R301").AutoFilter() | Out-Null
    $chain.Columns.Item("A").ColumnWidth = 14
    $chain.Columns.Item("B").ColumnWidth = 14
    $chain.Columns.Item("C").ColumnWidth = 12
    $chain.Columns.Item("D").ColumnWidth = 14
    $chain.Columns.Item("E").ColumnWidth = 16
    $chain.Columns.Item("F").ColumnWidth = 12
    $chain.Columns.Item("G").ColumnWidth = 20
    $chain.Columns.Item("H").ColumnWidth = 18
    $chain.Columns.Item("I").ColumnWidth = 12
    $chain.Columns.Item("J").ColumnWidth = 15
    $chain.Columns.Item("K").ColumnWidth = 14
    $chain.Columns.Item("L").ColumnWidth = 16
    $chain.Range("M:O").ColumnWidth = 14
    $chain.Range("P:Q").ColumnWidth = 10
    $chain.Columns.Item("R").ColumnWidth = 14
    $chain.Activate()
    $excel.ActiveWindow.SplitRow = 1
    $excel.ActiveWindow.FreezePanes = $true

    # Realce visual de linhas preenchidas na cadeia.
    $chain.Range("A2:R301").FormatConditions.Delete()
    $condition = $chain.Range("A2:R301").FormatConditions.Add(2, 0, '=$A2<>""')
    $condition.Interior.Color = $lightBlue

    $config.Activate()
    $excel.ActiveWindow.Zoom = 95
    $excel.DisplayAlerts = $true
    $workbook.SaveAs($OutputPath, 51)
    $workbook.Save()
    Write-Output "Workbook criado: $OutputPath"
    Write-Output "Planilhas: $($workbook.Worksheets.Item(1).Name), $($workbook.Worksheets.Item(2).Name), $($workbook.Worksheets.Item(3).Name)"
}
catch {
    $excel.DisplayAlerts = $true
    if ($null -ne $workbook) { $workbook.Close($false) }
    $excel.Quit()
    throw
}
