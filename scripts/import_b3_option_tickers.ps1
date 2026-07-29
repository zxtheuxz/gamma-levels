param(
    [string]$WorkbookPath = "E:\gamma levels\profit_rtd.xlsx",
    [int]$ExpiryCount = 4,
    [double]$StrikeBandPercent = 0.10,
    [int]$MaxRows = 300,
    [string]$CatalogPath = "E:\gamma levels\series_autorizadas_b3.zip",
    [switch]$ReuseCatalog
)

$ErrorActionPreference = "Stop"

function Get-B3AuthorizedSeriesDownload {
    param([string]$Destination)

    $pageUrl = "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/mercado-a-vista/opcoes/series-autorizadas/"
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $session.Cookies.Add((New-Object Net.Cookie("lumUserLocale", "pt_BR", "/", "www.b3.com.br")))
    $headers = @{
        Referer = $pageUrl
        "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138 Safari/537.36"
        Accept = "application/zip,application/octet-stream,*/*"
    }

    $page = Invoke-WebRequest -Uri $pageUrl -WebSession $session -Headers $headers -UseBasicParsing -TimeoutSec 180
    $match = [regex]::Match(
        [string]$page.Content,
        'href="(?<href>/lumis/portal/file/fileDownload\.jsp\?fileId=[^"]+)"[^>]*>\s*Lista Completa de Séries Autorizadas',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    if (-not $match.Success) {
        throw "A B3 não publicou o link da lista completa de séries autorizadas."
    }

    $downloadUrl = "https://www.b3.com.br$($match.Groups['href'].Value)"
    $response = Invoke-WebRequest -Uri $downloadUrl -WebSession $session -Headers $headers -UseBasicParsing -TimeoutSec 180
    if (-not ($response.Content -is [byte[]]) -or $response.RawContentLength -lt 1000) {
        throw "A B3 não devolveu o arquivo ZIP esperado."
    }
    [IO.File]::WriteAllBytes($Destination, $response.Content)
}

function Read-B3OptionSeries {
    param(
        [string]$ZipPath,
        [string]$UnderlyingTicker
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $root = [regex]::Match($UnderlyingTicker.ToUpperInvariant(), '^[A-Z]+').Value
    if ([string]::IsNullOrWhiteSpace($root)) {
        throw "Ticker de ativo-objeto inválido: $UnderlyingTicker"
    }

    $shareClass = if ($UnderlyingTicker -match '3$') { "ON" } else { "PN" }
    $result = New-Object System.Collections.Generic.List[object]
    $zip = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $entry = $zip.Entries | Where-Object { $_.FullName -like '*.txt' } | Select-Object -First 1
        if ($null -eq $entry) {
            throw "O ZIP da B3 não contém o arquivo TXT esperado."
        }

        $reader = New-Object IO.StreamReader($entry.Open(), [Text.Encoding]::GetEncoding(1252))
        try {
            while (($line = $reader.ReadLine()) -ne $null) {
                if (-not $line.StartsWith('02|')) { continue }
                $fields = $line.Split('|')
                if ($fields.Count -lt 18) { continue }

                $underlying = $fields[6].Trim()
                $class = $fields[7].Trim()
                if (-not $underlying.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { continue }
                if (-not $class.StartsWith($shareClass, [StringComparison]::OrdinalIgnoreCase)) { continue }

                $expiry = [datetime]::ParseExact($fields[17].Trim(), 'yyyyMMdd', [Globalization.CultureInfo]::InvariantCulture)
                if ($expiry.Date -lt [datetime]::Today) { continue }

                $strike = [double]::Parse($fields[16], [Globalization.CultureInfo]::InvariantCulture)
                $kind = if ($fields[3] -match 'COMPRA') { 'call' } elseif ($fields[3] -match 'VENDA') { 'put' } else { continue }
                $result.Add([pscustomobject]@{
                    Ticker = $fields[13].Trim()
                    Kind = $kind
                    Strike = $strike
                    Expiry = $expiry
                })
            }
        }
        finally {
            $reader.Dispose()
        }
    }
    finally {
        $zip.Dispose()
    }
    return $result
}

Add-Type -AssemblyName Microsoft.VisualBasic
$workbook = [Microsoft.VisualBasic.Interaction]::GetObject($WorkbookPath, $null)
$excel = $workbook.Application
$config = $workbook.Worksheets.Item("Config")
$raw = $workbook.Worksheets.Item("RTD_Profit")

$underlyingTicker = ([string]$config.Range("B3").Value2).Trim().ToUpperInvariant()
$spot = [double]$config.Range("B4").Value2
if ([string]::IsNullOrWhiteSpace($underlyingTicker)) {
    throw "Preencha Config!B3 com o ativo-objeto antes de importar."
}
if ($spot -le 0) {
    throw "O preço em Config!B4 ainda não chegou pelo RTD do Profit."
}

if (-not $ReuseCatalog -or -not (Test-Path -LiteralPath $CatalogPath)) {
    Get-B3AuthorizedSeriesDownload -Destination $CatalogPath
}
$allSeries = @(Read-B3OptionSeries -ZipPath $CatalogPath -UnderlyingTicker $underlyingTicker)
if ($allSeries.Count -eq 0) {
    throw "Nenhuma série autorizada foi encontrada para $underlyingTicker."
}

$expiries = @($allSeries | Select-Object -ExpandProperty Expiry -Unique | Sort-Object | Select-Object -First $ExpiryCount)
$lowerStrike = $spot * (1.0 - $StrikeBandPercent)
$upperStrike = $spot * (1.0 + $StrikeBandPercent)
$selected = @(
    $allSeries |
        Where-Object { $_.Expiry -in $expiries -and $_.Strike -ge $lowerStrike -and $_.Strike -le $upperStrike } |
        Sort-Object Expiry, Strike, Kind, Ticker |
        Group-Object Ticker |
        ForEach-Object { $_.Group[0] }
)

if ($selected.Count -gt $MaxRows) {
    $selected = @(
        $selected |
            Sort-Object @{ Expression = { [Math]::Abs($_.Strike - $spot) } }, Expiry, Kind, Ticker |
            Select-Object -First $MaxRows |
            Sort-Object Expiry, Strike, Kind, Ticker
    )
}
if ($selected.Count -eq 0) {
    throw "A seleção não encontrou séries dentro da faixa de strikes configurada."
}

$raw.Range("A2:A$($MaxRows + 1)").ClearContents()
$values = [object[,]]::new($selected.Count, 1)
for ($index = 0; $index -lt $selected.Count; $index++) {
    $values[$index, 0] = $selected[$index].Ticker
}
$raw.Range("A2").Resize($selected.Count, 1).Value2 = $values

$config.Range("A10").Value2 = "Séries carregadas"
$config.Range("B10").Value2 = $selected.Count
$config.Range("A11").Value2 = "Filtro automático"
$filterRange = $config.Range("B11:F11")
if (-not $filterRange.MergeCells) {
    $filterRange.Merge($false)
}
$config.Range("B11").Value2 = "$ExpiryCount vencimentos; strikes ±$([Math]::Round($StrikeBandPercent * 100))% do preço à vista"
$config.Range("A10:A11").Font.Bold = $true
$config.Range("B10:B11").Interior.Color = 14348258

$config.Range("A13").Value2 = "1. Digite o ticker do ativo-objeto em B3, por exemplo PETR4."
$config.Range("A14").Value2 = "2. Execute scripts\import_b3_option_tickers.ps1 para carregar os códigos automaticamente pela B3."
$config.Range("A15").Value2 = "3. Mantenha o Profit e esta planilha abertos; os dados RTD atualizam automaticamente."
$config.Range("A16").Value2 = "4. O importador usa os 4 vencimentos mais próximos e strikes até ±10% do preço à vista."
$config.Range("A17").Value2 = "5. Salve a planilha antes de executar a análise Python."
$config.Range("A18").Value2 = "6. Ajuste ExpiryCount e StrikeBandPercent no script quando desejar outra faixa."

$excel.CalculateFull()
$workbook.Save()
$raw.Activate()
$raw.Range("A2").Select() | Out-Null

Write-Output "Ativo: $underlyingTicker"
Write-Output "Preço à vista: $spot"
Write-Output "Séries B3 encontradas: $($allSeries.Count)"
Write-Output "Códigos carregados no Excel: $($selected.Count)"
Write-Output "Vencimentos: $($expiries.ForEach({ $_.ToString('yyyy-MM-dd') }) -join ', ')"
Write-Output "Faixa de strikes: $([Math]::Round($lowerStrike, 2)) a $([Math]::Round($upperStrike, 2))"
