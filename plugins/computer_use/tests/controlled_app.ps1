param([string]$StatePath, [string]$WindowTitle)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class DpiSetup {
    [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr value);
}
'@
[DpiSetup]::SetProcessDpiAwarenessContext([IntPtr](-4)) | Out-Null
$form = New-Object System.Windows.Forms.Form
$form.Text = $WindowTitle
$form.StartPosition = 'Manual'
$form.Location = New-Object System.Drawing.Point(100, 100)
$form.Size = New-Object System.Drawing.Size(600, 360)
$form.AutoScaleMode = 'Dpi'
$form.KeyPreview = $true
$inputBox = New-Object System.Windows.Forms.TextBox
$inputBox.AccessibleName = '验收输入'
$inputBox.Location = New-Object System.Drawing.Point(30, 40)
$inputBox.Size = New-Object System.Drawing.Size(440, 36)
$button = New-Object System.Windows.Forms.Button
$button.Text = '验证按钮'
$button.AccessibleName = '验证按钮'
$button.Location = New-Object System.Drawing.Point(30, 100)
$button.Size = New-Object System.Drawing.Size(160, 48)
$label = New-Object System.Windows.Forms.Label
$label.Location = New-Object System.Drawing.Point(30, 180)
$label.Size = New-Object System.Drawing.Size(440, 60)
$script:Clicks = 0
$script:Shortcut = $false
function Save-State {
    $label.Text = "点击: $script:Clicks 快捷键: $script:Shortcut 内容: $($inputBox.Text)"
    $data = @{ pid = $PID; window_id = $form.Handle.ToInt64(); text = $inputBox.Text; clicks = $script:Clicks; shortcut = $script:Shortcut }
    [IO.File]::WriteAllText($StatePath, ($data | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
}
$button.Add_Click({ $script:Clicks += 1; Save-State })
$inputBox.Add_TextChanged({ Save-State })
$form.Add_KeyDown({
    if ($_.Control -and $_.Shift -and $_.KeyCode -eq 'K') {
        $script:Shortcut = $true
        $_.Handled = $true
        $_.SuppressKeyPress = $true
        Save-State
    }
})
$form.Controls.AddRange(@($inputBox, $button, $label))
$form.Add_Shown({ Save-State })
[System.Windows.Forms.Application]::Run($form)
