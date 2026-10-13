; Custom NSIS hooks for FuncAssist
; Copies bundled FFmpeg directly to the root of AppData\Local\funcassist during installation

!macro NSIS_HOOK_POSTINSTALL
  DetailPrint "Configuring FFmpeg in application data root..."
  CreateDirectory "$LOCALAPPDATA\funcassist"
  IfFileExists "$INSTDIR\resources\bin\ffmpeg.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\resources\bin\ffmpeg.exe" "$LOCALAPPDATA\funcassist\ffmpeg.exe"
  IfFileExists "$INSTDIR\bin\ffmpeg.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\bin\ffmpeg.exe" "$LOCALAPPDATA\funcassist\ffmpeg.exe"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  Delete "$LOCALAPPDATA\funcassist\ffmpeg.exe"
!macroend
