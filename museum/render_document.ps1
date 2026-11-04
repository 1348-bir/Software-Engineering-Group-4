param([string]$Source, [string]$Output, [int]$PageLimit)
$ErrorActionPreference = 'Stop'
$app = $null
$doc = $null
$isSlides = [IO.Path]::GetExtension($Source) -in @('.ppt', '.pptx')
$ownsApp = $true
$oldSecurity = $null
$oldAlerts = $null
try {
    if ($isSlides) {
        $app = New-Object -ComObject PowerPoint.Application
        $ownsApp = $app.Presentations.Count -eq 0
        $oldSecurity = $app.AutomationSecurity
        $oldAlerts = $app.DisplayAlerts
        $app.AutomationSecurity = 3
        $app.DisplayAlerts = 1
        $doc = $app.Presentations.Open($Source, -1, 0, 0)
        if ($doc.Slides.Count -gt $PageLimit) { throw 'Document exceeds page limit' }
        for ($i = 1; $i -le $doc.Slides.Count; $i++) {
            $file = Join-Path $Output ('page-{0:000}.png' -f $i)
            $doc.Slides.Item($i).Export($file, 'PNG', 1440, [int](1440 * $doc.PageSetup.SlideHeight / $doc.PageSetup.SlideWidth))
        }
    } else {
        $app = New-Object -ComObject Word.Application
        $app.Visible = $false
        $app.DisplayAlerts = 0
        $app.AutomationSecurity = 3
        $app.Options.UpdateLinksAtOpen = $false
        $doc = $app.Documents.Open($Source, $false, $true, $false)
        $doc.Repaginate()
        if ($doc.ComputeStatistics(2) -gt $PageLimit) { throw 'Document exceeds page limit' }
        $doc.ExportAsFixedFormat((Join-Path $Output 'document.pdf'), 17)
    }
} finally {
    if ($null -ne $doc) {
        if ($isSlides) { $doc.Close() } else { $doc.Close(0) }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($doc)
    }
    if ($null -ne $app) {
        if ($ownsApp) { $app.Quit() }
        elseif ($isSlides) {
            $app.AutomationSecurity = $oldSecurity
            $app.DisplayAlerts = $oldAlerts
        }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($app)
    }
}
