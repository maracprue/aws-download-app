' Creates a desktop shortcut for the AWS S3 App with the correct icon.
' Double-click this file once to set up the shortcut — you won't need it again.

Dim fso, shell, appFolder, vbsPath, iconPath, desktopPath, lnkPath, shortcut

Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Resolve paths relative to this script's location
appFolder   = fso.GetParentFolderName(WScript.ScriptFullName)
vbsPath     = appFolder & "\launch_aws_app_silent.vbs"
iconPath    = appFolder & "\aws_download_app\assets\aws_app_icon.ico"
desktopPath = shell.SpecialFolders("Desktop")
lnkPath     = desktopPath & "\AWS S3 App.lnk"

' Delete old shortcut if it exists so Windows doesn't reuse the cached icon
If fso.FileExists(lnkPath) Then fso.DeleteFile lnkPath

' Clear the Windows icon cache so the new icon is picked up immediately
Dim cachePath
cachePath = shell.ExpandEnvironmentStrings("%LocalAppData%\IconCache.db")
If fso.FileExists(cachePath) Then
    On Error Resume Next
    fso.DeleteFile cachePath
    On Error GoTo 0
End If

' Create the shortcut with the new icon
Set shortcut = shell.CreateShortcut(lnkPath)
shortcut.TargetPath       = vbsPath
shortcut.WorkingDirectory = appFolder
shortcut.IconLocation     = iconPath & ", 0"
shortcut.Description      = "Launch the AWS S3 Download & Upload App"
shortcut.Save()

' Restart explorer to reload the icon cache
shell.Run "taskkill /f /im explorer.exe", 0, True
shell.Run "explorer.exe", 1, False

MsgBox "Shortcut created on your Desktop!" & vbCrLf & vbCrLf & _
       "Double-click 'AWS S3 App' on the Desktop to launch the app.", _
       vbInformation, "AWS S3 App"

Set shortcut = Nothing
Set shell    = Nothing
Set fso      = Nothing
