param([ValidateSet('Files', 'Folder')][string]$Mode = 'Files')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
if ($Mode -eq 'Files') {
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = 'Marginalia - Select course materials'
    $dialog.Multiselect = $true
    $dialog.Filter = 'Learning materials|*.pdf;*.doc;*.docx;*.ppt;*.pptx;*.xls;*.xlsx;*.csv;*.txt;*.md;*.png;*.jpg;*.jpeg;*.webp;*.gif;*.zip;*.7z;*.rar|All files|*.*'
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        ConvertTo-Json -InputObject @($dialog.FileNames) -Compress
    } else { '[]' }
} else {
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Marginalia - Select a folder of course materials'
    $dialog.ShowNewFolderButton = $false
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        ConvertTo-Json -InputObject @($dialog.SelectedPath) -Compress
    } else { '[]' }
}
$dialog.Dispose()
