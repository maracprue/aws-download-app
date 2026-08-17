' Silently launches the AWS S3 App without showing a terminal window.
' Create a desktop shortcut pointing to THIS file.
' Set the shortcut icon to: aws_download_app\assets\aws_app_icon.ico

Dim fso, batPath
Set fso    = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

' Resolve the .bat path relative to THIS script's actual location
batPath = fso.GetParentFolderName(WScript.ScriptFullName) & "\launch_aws_app.bat"
WshShell.Run Chr(34) & batPath & Chr(34), 0, False

Set fso      = Nothing
Set WshShell = Nothing
