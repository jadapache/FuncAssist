; Custom NSIS hooks for FuncAssist
; Copies bundled FFmpeg and Standalone Backend directly to AppData\Local\funcassist during installation

!macro NSIS_HOOK_POSTINSTALL
  DetailPrint "Configuring application runtime files in data root..."
  CreateDirectory "$LOCALAPPDATA\funcassist"

  ; FFmpeg binary
  IfFileExists "$INSTDIR\resources\bin\ffmpeg.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\resources\bin\ffmpeg.exe" "$LOCALAPPDATA\funcassist\ffmpeg.exe"
  IfFileExists "$INSTDIR\resources\ffmpeg.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\resources\ffmpeg.exe" "$LOCALAPPDATA\funcassist\ffmpeg.exe"
  IfFileExists "$INSTDIR\bin\ffmpeg.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\bin\ffmpeg.exe" "$LOCALAPPDATA\funcassist\ffmpeg.exe"
  IfFileExists "$INSTDIR\ffmpeg.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\ffmpeg.exe" "$LOCALAPPDATA\funcassist\ffmpeg.exe"

  ; Standalone Python FastAPI backend binary
  IfFileExists "$INSTDIR\resources\bin\funcassist-backend.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\resources\bin\funcassist-backend.exe" "$LOCALAPPDATA\funcassist\funcassist-backend.exe"
  IfFileExists "$INSTDIR\resources\funcassist-backend.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\resources\funcassist-backend.exe" "$LOCALAPPDATA\funcassist\funcassist-backend.exe"
  IfFileExists "$INSTDIR\bin\funcassist-backend.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\bin\funcassist-backend.exe" "$LOCALAPPDATA\funcassist\funcassist-backend.exe"
  IfFileExists "$INSTDIR\funcassist-backend.exe" 0 +2
    CopyFiles /SILENT "$INSTDIR\funcassist-backend.exe" "$LOCALAPPDATA\funcassist\funcassist-backend.exe"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  Delete "$LOCALAPPDATA\funcassist\ffmpeg.exe"
  Delete "$LOCALAPPDATA\funcassist\funcassist-backend.exe"
!macroend
