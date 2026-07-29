param(
    [string]$WorkbookPath = "E:\gamma levels\profit_rtd.xlsx"
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName Microsoft.VisualBasic
$workbook = [Microsoft.VisualBasic.Interaction]::GetObject($WorkbookPath, $null)
$excel = $workbook.Application

$config = $workbook.Worksheets.Item("Config")
$raw = $workbook.Worksheets.Item("RTD_Profit")
$chain = $workbook.Worksheets.Item("Cadeia")

$config.Range("B5:B6").NumberFormatLocal = "0,00%"
$config.Range("B4").NumberFormatLocal = "0,00"
$config.Range("B7:B9").NumberFormatLocal = "#.##0"
$config.Range("B8").NumberFormatLocal = "aaaa-mm-dd"
for ($row = 13; $row -le 18; $row++) {
    $instructionRange = $config.Range("A${row}:F${row}")
    if (-not $instructionRange.MergeCells) {
        $instructionRange.Merge($false)
    }
}
$config.Range("A13:F18").WrapText = $true
$config.Range("A13:F18").RowHeight = 24
$config.Range("B21:F22").Font.Size = 9
$config.Range("B21:F22").WrapText = $true
$config.Rows.Item(21).RowHeight = 28
$config.Rows.Item(22).RowHeight = 28

$raw.Range("B2:D301").NumberFormatLocal = "0,00"
$raw.Range("E2:G301").NumberFormatLocal = "#.##0"
$raw.Range("H2:H301").NumberFormatLocal = "0,00"
$raw.Range("I2:I301").NumberFormatLocal = "aaaa-mm-dd"
$raw.Range("J2:O301").NumberFormatLocal = "0,0000"
$raw.Range("P2:P301").NumberFormatLocal = "hh:mm:ss"
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

$chain.Range("C2:C301").NumberFormatLocal = "0,00"
$chain.Range("H2:J301").NumberFormatLocal = "0,00"
$chain.Range("P2:Q301").NumberFormatLocal = "0,00"
$chain.Range("D2:D301").NumberFormatLocal = "aaaa-mm-dd"
$chain.Range("E2:F301").NumberFormatLocal = "#.##0"
$chain.Range("G2:G301").NumberFormatLocal = "0,0000"
$chain.Range("K2:O301").NumberFormatLocal = "0,0000"
$chain.Range("R2:R301").NumberFormatLocal = "hh:mm:ss"
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

$config.Activate()
$workbook.Save()
Write-Output "Workbook atualizado e salvo: $($workbook.FullName)"
