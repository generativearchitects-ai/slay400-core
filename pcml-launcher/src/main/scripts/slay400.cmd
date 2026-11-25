@echo off
rem The slay400 launcher for Windows (kickoff 17). Finds Java, resolves its own location (%~dp0, which cmd.exe
rem already gives as the real folder of this file), and runs the packaged jar with the given arguments, untouched
rem (%*). Reads JAVA_HOME, PATH, JAVA_OPTS and SLAY400_OPTS; nothing else in the environment changes what it does.
rem No network access, no update check, no file written.
setlocal enabledelayedexpansion

rem Not used by the tool itself for anything else (which uses 0-4): one documented value for "Java is missing or too old".
set "NO_JAVA=70"

set "JAVA_EXE="
if defined JAVA_HOME (
  if exist "%JAVA_HOME%\bin\java.exe" set "JAVA_EXE=%JAVA_HOME%\bin\java.exe"
)
if not defined JAVA_EXE (
  for %%I in (java.exe) do (
    if not defined JAVA_EXE set "JAVA_EXE=%%~$PATH:I"
  )
)
if not defined JAVA_EXE (
  echo slay400: Java was not found ^(checked JAVA_HOME, then PATH^); slay400 needs Java 21 or later. 1>&2
  exit /b %NO_JAVA%
)

rem Not just the first line: when JAVA_TOOL_OPTIONS or _JAVA_OPTIONS is set (common in containers and CI images),
rem the JVM prints "Picked up JAVA_TOOL_OPTIONS: ..." before the version, even for an empty value.
set "VERSION_LINE="
set "FIRST_LINE="
for /f "delims=" %%L in ('""%JAVA_EXE%"" -version 2^>^&1') do (
  if not defined FIRST_LINE set "FIRST_LINE=%%L"
  echo %%L| findstr /c:"version" >nul
  if not errorlevel 1 if not defined VERSION_LINE set "VERSION_LINE=%%L"
)
if not defined VERSION_LINE set "VERSION_LINE=%FIRST_LINE%"

set "QUOTED="
for /f tokens^=2delims^=^" %%V in ("%VERSION_LINE%") do set "QUOTED=%%V"

for /f "tokens=1,2 delims=." %%A in ("%QUOTED%") do (
  set "PART1=%%A"
  set "PART2=%%B"
)
if "%PART1%"=="1" (
  set "MAJOR=%PART2%"
) else (
  set "MAJOR=%PART1%"
)

set "BAD="
if "%MAJOR%"=="" set "BAD=1"
echo %MAJOR%| findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 set "BAD=1"
if defined BAD (
  echo slay400: could not read a Java version from: %VERSION_LINE% 1>&2
  exit /b %NO_JAVA%
)

if %MAJOR% LSS 21 (
  echo slay400: found Java %QUOTED% ^(%JAVA_EXE%^), but slay400 needs Java 21 or later. 1>&2
  exit /b %NO_JAVA%
)

set "ROOT=%~dp0.."
set "JAR="
for %%F in ("%ROOT%\lib\pcml-cli-*.jar") do set "JAR=%%F"

"%JAVA_EXE%" %JAVA_OPTS% %SLAY400_OPTS% -jar "%JAR%" %*
exit /b %ERRORLEVEL%
