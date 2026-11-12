# Convert a .docx to .pdf with Microsoft Word (same renderer the candidate used to check previews).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File docx2pdf.ps1 <file.docx>
param([Parameter(Mandatory = $true)][string]$Docx)
$ErrorActionPreference = 'Stop'
$in = (Resolve-Path $Docx).Path
$out = [System.IO.Path]::ChangeExtension($in, '.pdf')
if (Test-Path $out) { Remove-Item $out -Force }
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($in, $false, $true)
    $doc.SaveAs([ref]$out, [ref]17)   # 17 = wdFormatPDF
    $doc.Close([ref]0)
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
Write-Output "Wrote $out"
