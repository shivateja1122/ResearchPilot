param(
    [string]$PdfPath = "ResearchPilot_Architecture_Deep_Dive.pdf",
    [string]$OutputDir = "pdf_preview"
)

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime] | Out-Null

$allAsTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' }
$asTaskGeneric = ($allAsTask | Where-Object { $_.ContainsGenericParameters -and $_.GetParameters().Count -eq 1 })[0]
$asTaskAction = ($allAsTask | Where-Object { -not $_.ContainsGenericParameters -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' })[0]

function Await-WinRT($winRtTask, $resultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($resultType)
    $netTask = $asTask.Invoke($null, @($winRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

function Await-Action($winRtAction) {
    $netTask = $asTaskAction.Invoke($null, @($winRtAction))
    $netTask.Wait(-1) | Out-Null
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$resolvedPath = (Resolve-Path $PdfPath).Path
$fileOp = [Windows.Storage.StorageFile]::GetFileFromPathAsync($resolvedPath)
$file = Await-WinRT $fileOp ([Windows.Storage.StorageFile])

$docOp = [Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)
$pdfDoc = Await-WinRT $docOp ([Windows.Data.Pdf.PdfDocument])

Write-Host "Total pages in PDF: $($pdfDoc.PageCount)"

for ($i = 0; $i -lt $pdfDoc.PageCount; $i++) {
    $page = $pdfDoc.GetPage($i)
    $memStream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    $renderOp = $page.RenderToStreamAsync($memStream)
    Await-Action $renderOp

    $netStream = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($memStream)
    $netStream.Position = 0
    $img = [System.Drawing.Image]::FromStream($netStream)
    $outPath = Join-Path $OutputDir "page_$($i + 1).png"
    $img.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $img.Dispose()
    $netStream.Dispose()
    $memStream.Dispose()
    Write-Host "Successfully exported $outPath"
}
