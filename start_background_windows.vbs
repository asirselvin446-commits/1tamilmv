Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strDir
WshShell.Run """" & strDir & "\run_bot.bat""", 0, False
MsgBox "1TamilVT-TG Bot is now running silently in the background with auto-restart! Check logs\bot.log for live output.", 64, "1TamilVT-TG Bot"
