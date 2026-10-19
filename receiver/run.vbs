' Запуск получателя сообщений без консоли
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

' Запуск pythonw (оконный режим без консоли)
WshShell.Run "pythonw receive.py", 0, False
