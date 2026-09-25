# Android CI

Android CI runs real unit tests and builds the Debug APK on the repository-scoped self-hosted macOS ARM64 Runner `remember-me-jitian-mac-arm64`. The job uploads the generated APK as a seven-day workflow artifact. It does not contain a placeholder or success override: a missing toolchain, failed test, failed build, or missing APK fails the job.

## Why the repository uses a self-hosted Runner

The GitHub-hosted Ubuntu job repeatedly failed before compilation while resolving Android Gradle Plugin `8.7.3`. The same source builds locally. Attempts using the configured Huawei/Aliyun mirrors and official Google/Maven repositories did not produce a reliable hosted-runner path in the available network environment. Issue #17 tracks this infrastructure decision and its history.

The self-hosted Runner uses the verified local Android toolchain and the trusted local network proxy. This is an infrastructure workaround, not a test waiver: CI still checks out a clean workspace, runs the Gradle Wrapper, executes unit tests, builds the APK, and fails closed.

## Runner and repository strategy

- Required labels: `self-hosted`, `macOS`, `ARM64`, `remember-me`.
- Required toolchain: JDK 17, Android SDK Platform 35, Build Tools 35.0.0, and the repository Gradle 8.9 Wrapper.
- The Runner service provides `JAVA_HOME`, `ANDROID_HOME`, `ANDROID_SDK_ROOT`, and proxy settings through its local `.env`; that file is outside the repository and contains no application/provider credential.
- Maven repositories remain centralized in `settings.gradle.kts`. Feature branches must not add private repository URLs, credentials, or per-module repository blocks.
- Gradle runs with `--no-daemon` so a persistent CI host does not retain a build daemon between jobs.

## Security boundary

Self-hosted CI executes only pushes and Pull Requests whose head repository is this repository. Fork Pull Requests are skipped so untrusted fork code cannot run on the developer machine. The service explicitly clears inherited AI-provider and SSH-agent environment variables, and the workflow verifies that they are empty before running project code.

Repository collaborators are still trusted code executors on this Runner. Code Owner review is available as feedback but is not required before merge. Do not add steps that print the environment, home directory contents, credential stores, or unrelated host state.

## Local reproduction

From `apps/android`:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
export ANDROID_HOME="$ANDROID_SDK_ROOT"
./gradlew --no-daemon test assembleDebug --stacktrace
```

The expected artifact is `app/build/outputs/apk/debug/app-debug.apk`. A correct change should produce a green job; deliberately breaking a Kotlin source or test must produce a red job. The job reports build health but is not a required branch-protection check.

## Operations

The Runner is installed as a user LaunchAgent. Check it with:

```bash
cd "$HOME/.local/share/github-actions-runner/remember-me"
./svc.sh status
```

If the host is offline, CI remains queued rather than silently passing. Restore the service and rerun the workflow; do not replace the job with a no-op fallback.
