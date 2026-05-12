@echo off
setlocal enabledelayedexpansion

rem ---------------------------------------------------------------------------
rem Release pyspeks to PyPI (Windows).
rem
rem Usage:
rem   scripts\release.cmd ^<version^> [--test] [--skip-tests] [--dry-run]
rem
rem Examples:
rem   scripts\release.cmd 0.2.0              :: release to PyPI
rem   scripts\release.cmd 0.2.0 --test       :: release to TestPyPI
rem   scripts\release.cmd 0.2.0 --dry-run    :: everything except upload/push
rem
rem Credentials: configure %USERPROFILE%\.pypirc or set TWINE_USERNAME /
rem TWINE_PASSWORD (use __token__ as username and your PyPI API token as
rem password).
rem ---------------------------------------------------------------------------

set "VERSION="
set "USE_TEST=0"
set "SKIP_TESTS=0"
set "DRY_RUN=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--test" (
    set "USE_TEST=1"
    shift
    goto parse_args
)
if /I "%~1"=="--skip-tests" (
    set "SKIP_TESTS=1"
    shift
    goto parse_args
)
if /I "%~1"=="--dry-run" (
    set "DRY_RUN=1"
    shift
    goto parse_args
)
if /I "%~1"=="-h" goto print_help
if /I "%~1"=="--help" goto print_help
if not defined VERSION (
    set "VERSION=%~1"
    shift
    goto parse_args
)
echo ERROR: multiple versions given: !VERSION! and %~1 1>&2
exit /b 1

:print_help
echo Usage: %~nx0 ^<version^> [--test] [--skip-tests] [--dry-run]
exit /b 0

:args_done
if not defined VERSION (
    echo ERROR: version is required. 1>&2
    echo Usage: %~nx0 ^<version^> [--test] [--skip-tests] [--dry-run] 1>&2
    exit /b 1
)

rem Validate semver via PowerShell (cmd regex support is too weak).
powershell -NoProfile -Command ^
    "if ('%VERSION%' -notmatch '^[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.+-]+)?$') { exit 1 }"
if errorlevel 1 (
    echo ERROR: invalid version: '%VERSION%' ^(expected MAJOR.MINOR.PATCH[-pre]^) 1>&2
    exit /b 1
)

rem ---------------------------------------------------------------------------
rem Locate project root
rem ---------------------------------------------------------------------------

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%\.." || (
    echo ERROR: could not change to project root 1>&2
    exit /b 1
)
set "ROOT=%CD%"

set "PYPROJECT=%ROOT%\pyproject.toml"
set "INIT_FILE=%ROOT%\speks\__init__.py"

if not exist "%PYPROJECT%" (
    echo ERROR: pyproject.toml not found at %PYPROJECT% 1>&2
    popd & exit /b 1
)
if not exist "%INIT_FILE%" (
    echo ERROR: speks\__init__.py not found at %INIT_FILE% 1>&2
    popd & exit /b 1
)

rem ---------------------------------------------------------------------------
rem Preflight: clean tree, latest pulled, tag not already used
rem ---------------------------------------------------------------------------

echo ^>^>^> Preflight checks

for /f "delims=" %%G in ('git status --porcelain') do (
    echo ERROR: working tree is dirty. Commit or stash before releasing. 1>&2
    popd & exit /b 1
)

for /f "delims=" %%G in ('git rev-parse --abbrev-ref HEAD') do set "CURRENT_BRANCH=%%G"
if /I not "!CURRENT_BRANCH!"=="main" (
    echo WARNING: you are on branch '!CURRENT_BRANCH!', not 'main'.
    set /p "ANS=Continue anyway? [y/N] "
    if /I not "!ANS!"=="y" if /I not "!ANS!"=="yes" (
        echo Aborted.
        popd & exit /b 1
    )
)

echo ^>^>^> Fetching origin
git fetch origin --tags
if errorlevel 1 (
    echo ERROR: git fetch failed 1>&2
    popd & exit /b 1
)

git rev-parse -q --verify "refs/tags/v%VERSION%" >nul 2>&1
if not errorlevel 1 (
    echo ERROR: tag v%VERSION% already exists locally. 1>&2
    popd & exit /b 1
)

git ls-remote --exit-code --tags origin "refs/tags/v%VERSION%" >nul 2>&1
if not errorlevel 1 (
    echo ERROR: tag v%VERSION% already exists on origin. 1>&2
    popd & exit /b 1
)

rem ---------------------------------------------------------------------------
rem Tests + type checks
rem ---------------------------------------------------------------------------

if "%SKIP_TESTS%"=="0" (
    echo ^>^>^> Running mypy
    python -m mypy speks\
    if errorlevel 1 (
        echo ERROR: mypy failed 1>&2
        popd & exit /b 1
    )

    echo ^>^>^> Running unit tests ^(excluding e2e^)
    python -m pytest tests/ -q
    if errorlevel 1 (
        echo ERROR: tests failed 1>&2
        popd & exit /b 1
    )
) else (
    echo WARNING: Skipping tests ^(--skip-tests^)
)

rem ---------------------------------------------------------------------------
rem Bump version in pyproject.toml + __init__.py via PowerShell
rem ---------------------------------------------------------------------------

echo ^>^>^> Bumping version to %VERSION%

powershell -NoProfile -Command ^
    "$p = '%PYPROJECT%'; (Get-Content -Raw $p) -replace '(?m)^version = \"[^\"]+\"', ('version = \"%VERSION%\"') | Set-Content -NoNewline $p"
if errorlevel 1 (
    echo ERROR: failed to update pyproject.toml 1>&2
    popd & exit /b 1
)

powershell -NoProfile -Command ^
    "$p = '%INIT_FILE%'; (Get-Content -Raw $p) -replace '(?m)^__version__ = \"[^\"]+\"', ('__version__ = \"%VERSION%\"') | Set-Content -NoNewline $p"
if errorlevel 1 (
    echo ERROR: failed to update speks\__init__.py 1>&2
    popd & exit /b 1
)

rem Verify substitution.
findstr /R /C:"^version = \"%VERSION%\"" "%PYPROJECT%" >nul
if errorlevel 1 (
    echo ERROR: version bump in pyproject.toml failed 1>&2
    popd & exit /b 1
)
findstr /R /C:"^__version__ = \"%VERSION%\"" "%INIT_FILE%" >nul
if errorlevel 1 (
    echo ERROR: version bump in speks\__init__.py failed 1>&2
    popd & exit /b 1
)

echo Version bumped. Diff:
git --no-pager diff -- "%PYPROJECT%" "%INIT_FILE%"

set /p "ANS=Commit and tag this change? [y/N] "
if /I not "!ANS!"=="y" if /I not "!ANS!"=="yes" (
    echo Aborted by user. Reverting working-copy changes.
    git checkout -- "%PYPROJECT%" "%INIT_FILE%"
    popd & exit /b 1
)

rem ---------------------------------------------------------------------------
rem Commit + tag
rem ---------------------------------------------------------------------------

echo ^>^>^> Committing
git add "%PYPROJECT%" "%INIT_FILE%"
git commit -m "release: v%VERSION%"
if errorlevel 1 (
    echo ERROR: git commit failed 1>&2
    popd & exit /b 1
)

echo ^>^>^> Tagging v%VERSION%
git tag -a "v%VERSION%" -m "Release v%VERSION%"
if errorlevel 1 (
    echo ERROR: git tag failed 1>&2
    popd & exit /b 1
)

rem ---------------------------------------------------------------------------
rem Build sdist + wheel
rem ---------------------------------------------------------------------------

echo ^>^>^> Cleaning build artefacts
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
for /d %%D in (*.egg-info) do rmdir /s /q "%%D"

echo ^>^>^> Ensuring build + twine are installed
python -m pip install --upgrade build twine >nul
if errorlevel 1 (
    echo ERROR: pip install failed 1>&2
    popd & exit /b 1
)

echo ^>^>^> Building sdist + wheel
python -m build
if errorlevel 1 (
    echo ERROR: build failed 1>&2
    popd & exit /b 1
)

echo ^>^>^> Validating distributions
python -m twine check dist\*
if errorlevel 1 (
    echo ERROR: twine check failed 1>&2
    popd & exit /b 1
)

echo Distributions ready:
dir /b dist

rem ---------------------------------------------------------------------------
rem Upload
rem ---------------------------------------------------------------------------

if "%DRY_RUN%"=="1" (
    echo --dry-run: skipping upload and git push.
    echo Tag v%VERSION% was created locally. Drop it with:
    echo     git tag -d v%VERSION% ^&^& git reset --hard HEAD^^
    popd & exit /b 0
)

if "%USE_TEST%"=="1" (
    set "REPO_NAME=TestPyPI"
    set "UPLOAD_ARGS=--repository testpypi"
) else (
    set "REPO_NAME=PyPI"
    set "UPLOAD_ARGS="
)

echo About to upload to !REPO_NAME!.
set /p "ANS=Proceed with upload? [y/N] "
if /I not "!ANS!"=="y" if /I not "!ANS!"=="yes" (
    echo Aborted before upload.
    popd & exit /b 1
)

echo ^>^>^> Uploading to !REPO_NAME!
python -m twine upload !UPLOAD_ARGS! dist\*
if errorlevel 1 (
    echo ERROR: twine upload failed 1>&2
    popd & exit /b 1
)

rem ---------------------------------------------------------------------------
rem Push commit + tag
rem ---------------------------------------------------------------------------

set /p "ANS=Push commit and tag to origin? [y/N] "
if /I not "!ANS!"=="y" if /I not "!ANS!"=="yes" (
    echo Upload succeeded but commit/tag not pushed. Run when ready:
    echo     git push origin !CURRENT_BRANCH! --follow-tags
    popd & exit /b 0
)

echo ^>^>^> Pushing
git push origin "!CURRENT_BRANCH!" --follow-tags
if errorlevel 1 (
    echo ERROR: git push failed 1>&2
    popd & exit /b 1
)

echo Done. v%VERSION% released to !REPO_NAME!.
popd
endlocal
exit /b 0
