package ai.generativearchitects.slay400.launcher;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;
import org.junit.jupiter.api.io.TempDir;

/**
 * Kickoff 17: the launch scripts, exercised directly (not through the archive, which {@code DistributionArchiveIT}
 * checks) -- a tiny compiled "echo its arguments and exit with the given status" jar stands in for pcml-cli's.
 */
class LauncherScriptTest {

    private static final Path POSIX_SCRIPT = Path.of("src/main/scripts/slay400");
    private static final Path WINDOWS_SCRIPT = Path.of("src/main/scripts/slay400.cmd");
    private static final Path JAVA_HOME = Path.of(System.getProperty("java.home"));

    private record Run(int exit, String out, String err) {
    }

    private static Path echoJar;

    /** Compiles and packs a program that prints each argument on its own line, bracketed, and exits with $0 (or 0). */
    @BeforeAll
    static void compileEchoJar(@TempDir Path shared) throws IOException, InterruptedException {
        Path source = shared.resolve("EchoMain.java");
        Files.writeString(source, """
                public final class EchoMain {
                    public static void main(String[] args) {
                        int exit = 0;
                        for (String arg : args) {
                            if (arg.matches("-?\\\\d+") && exit == 0 && args.length > 0 && arg.equals(args[args.length - 1])) {
                                exit = Integer.parseInt(arg);
                            }
                            System.out.println("[" + arg + "]");
                        }
                        System.exit(exit);
                    }
                }
                """);
        run(shared, JAVA_HOME.resolve("bin").resolve("javac").toString(), source.toString());
        echoJar = shared.resolve("echo.jar");
        run(shared, JAVA_HOME.resolve("bin").resolve("jar").toString(), "cfe", echoJar.toString(), "EchoMain", "-C",
                shared.toString(), "EchoMain.class");
    }

    private static Run run(Path workingDirectory, String... command) throws IOException, InterruptedException {
        return runWithEnv(workingDirectory, java.util.Map.of(), command);
    }

    private static Run runWithEnv(Path workingDirectory, java.util.Map<String, String> env, String... command) throws IOException, InterruptedException {
        ProcessBuilder builder = new ProcessBuilder(command).directory(workingDirectory.toFile());
        env.forEach((key, value) -> {
            if (value == null) {
                builder.environment().remove(key);
            } else {
                builder.environment().put(key, value);
            }
        });
        Process process = builder.start();
        byte[] out = process.getInputStream().readAllBytes();
        byte[] err = process.getErrorStream().readAllBytes();
        assertThat(process.waitFor(60, TimeUnit.SECONDS)).isTrue();
        return new Run(process.exitValue(), new String(out, StandardCharsets.UTF_8), new String(err, StandardCharsets.UTF_8));
    }

    /** {@code root/bin/<launcher>} and {@code root/lib/<echo jar>}, the shape the real archive gives the script. */
    private static Path installation(Path dir, boolean posix) throws IOException {
        Path bin = dir.resolve("bin");
        Files.createDirectories(bin);
        Path lib = dir.resolve("lib");
        Files.createDirectories(lib);
        Files.copy(echoJar, lib.resolve("pcml-cli-TEST.jar"));
        if (posix) {
            Path script = bin.resolve("slay400");
            Files.copy(POSIX_SCRIPT, script);
            Files.setPosixFilePermissions(script, EnumSet.of(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE,
                    PosixFilePermission.OWNER_EXECUTE, PosixFilePermission.GROUP_READ, PosixFilePermission.GROUP_EXECUTE,
                    PosixFilePermission.OTHERS_READ, PosixFilePermission.OTHERS_EXECUTE));
        } else {
            Files.copy(WINDOWS_SCRIPT, bin.resolve("slay400.cmd"));
        }
        return bin;
    }

    // ---- POSIX

    @Test
    @EnabledOnOs({OS.LINUX, OS.MAC})
    void argumentsWithSpacesQuotesAndNonAsciiArriveUnchangedAndTheExitStatusIsTheJarsOnPosix(@TempDir Path dir) throws Exception {
        Path bin = installation(dir, true);
        Run run = run(dir, bin.resolve("slay400").toString(), "a b", "$HOME", "quoted 'inner' \"outer\"", "", "café", "7");
        assertThat(run.exit()).isEqualTo(7);
        assertThat(run.out()).isEqualTo("[a b]\n[$HOME]\n[quoted 'inner' \"outer\"]\n[]\n[café]\n[7]\n");
        assertThat(run.err()).isEmpty();
    }

    @Test
    @EnabledOnOs({OS.LINUX, OS.MAC})
    void aSymbolicLinkOnThePathWorksOnPosix(@TempDir Path dir) throws Exception {
        Path bin = installation(dir, true);
        Path linkDir = dir.resolve("on-path");
        Files.createDirectories(linkDir);
        Files.createSymbolicLink(linkDir.resolve("slay400"), bin.resolve("slay400"));
        Run run = run(dir, linkDir.resolve("slay400").toString(), "0");
        assertThat(run.exit()).isZero();
        assertThat(run.out()).isEqualTo("[0]\n");
    }

    @Test
    @EnabledOnOs({OS.LINUX, OS.MAC})
    void noJavaOnPathOrJavaHomeGivesOneSentenceAndExitStatus70(@TempDir Path dir) throws Exception {
        Path bin = installation(dir, true);
        Run run = runWithEnv(dir, java.util.Map.of("PATH", "/does/not/exist", "JAVA_HOME", ""), bin.resolve("slay400").toString());
        assertThat(run.exit()).isEqualTo(70);
        assertThat(run.err().lines().toList()).hasSize(1);
        assertThat(run.err()).contains("Java was not found").contains("Java 21 or later");
        assertThat(run.out()).isEmpty();
    }

    @Test
    @EnabledOnOs({OS.LINUX, OS.MAC})
    void javaOlderThan21GivesOneSentenceAndExitStatus70AndJavaHomeWinsOverPath(@TempDir Path dir) throws Exception {
        Path oldJavaHome = dir.resolve("old-java");
        Path oldJavaBin = oldJavaHome.resolve("bin");
        Files.createDirectories(oldJavaBin);
        Path oldJava = oldJavaBin.resolve("java");
        Files.writeString(oldJava, "#!/bin/sh\necho 'java version \"1.8.0_392\"'\n");
        Files.setPosixFilePermissions(oldJava, EnumSet.of(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_EXECUTE));
        Path bin = installation(dir, true);
        Run run = runWithEnv(dir, java.util.Map.of("JAVA_HOME", oldJavaHome.toString()), bin.resolve("slay400").toString());
        assertThat(run.exit()).isEqualTo(70);
        assertThat(run.err()).contains("found Java 1.8.0_392").contains("Java 21 or later");
    }

    @Test
    @EnabledOnOs({OS.LINUX, OS.MAC})
    void javaOptsAndSlay400OptsReachTheJvmOnPosix(@TempDir Path dir) throws Exception {
        Path bin = installation(dir, true);
        Run run = runWithEnv(dir, java.util.Map.of("JAVA_OPTS", "-Dkickoff17.a=1", "SLAY400_OPTS", "-Dkickoff17.b=2"),
                bin.resolve("slay400").toString(), "0");
        assertThat(run.exit()).isZero();
    }

    /**
     * Review point 1: JAVA_TOOL_OPTIONS or _JAVA_OPTIONS, common in containers, CI images and company machines,
     * make the JVM print "Picked up ..." as the first line of {@code java -version}, even for an empty value; the
     * script must still find the real version line, not just the first one.
     */
    @Test
    @EnabledOnOs({OS.LINUX, OS.MAC})
    void javaToolOptionsAndUnderscoreJavaOptionsDoNotBreakVersionDetectionOnPosix(@TempDir Path dir) throws Exception {
        Path bin = installation(dir, true);
        for (String value : List.of("-Xmx128m", "")) {
            Run withToolOptions = runWithEnv(dir, java.util.Map.of("JAVA_TOOL_OPTIONS", value), bin.resolve("slay400").toString(), "0");
            assertThat(withToolOptions.exit()).as("JAVA_TOOL_OPTIONS=[%s]: %s", value, withToolOptions.err()).isZero();
            Run withJavaOptions = runWithEnv(dir, java.util.Map.of("_JAVA_OPTIONS", value), bin.resolve("slay400").toString(), "0");
            assertThat(withJavaOptions.exit()).as("_JAVA_OPTIONS=[%s]: %s", value, withJavaOptions.err()).isZero();
        }
    }

    /** The exact reproduction of review point 1: an old Java that also picks up JAVA_TOOL_OPTIONS must still be caught. */
    @Test
    @EnabledOnOs({OS.LINUX, OS.MAC})
    void javaOlderThan21IsStillDetectedWithAPickedUpToolOptionsLineOnPosix(@TempDir Path dir) throws Exception {
        Path oldJavaHome = dir.resolve("old-java");
        Path oldJavaBin = oldJavaHome.resolve("bin");
        Files.createDirectories(oldJavaBin);
        Path oldJava = oldJavaBin.resolve("java");
        Files.writeString(oldJava, "#!/bin/sh\necho 'Picked up JAVA_TOOL_OPTIONS: -Xmx128m' >&2\necho 'java version \"1.8.0_392\"'\n");
        Files.setPosixFilePermissions(oldJava, EnumSet.of(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_EXECUTE));
        Path bin = installation(dir, true);
        Run run = runWithEnv(dir, java.util.Map.of("JAVA_HOME", oldJavaHome.toString(), "JAVA_TOOL_OPTIONS", "-Xmx128m"),
                bin.resolve("slay400").toString());
        assertThat(run.exit()).isEqualTo(70);
        assertThat(run.err()).contains("found Java 1.8.0_392").contains("Java 21 or later");
    }

    // ---- Windows

    @Test
    @EnabledOnOs(OS.WINDOWS)
    void argumentsWithSpacesAndQuotesArriveUnchangedAndTheExitStatusIsTheJarsOnWindows(@TempDir Path dir) throws Exception {
        Path bin = installation(dir, false);
        Run run = run(dir, bin.resolve("slay400.cmd").toString(), "a b", "quoted \"\"inner\"\"", "7");
        assertThat(run.exit()).isEqualTo(7);
        assertThat(run.out()).contains("[a b]").contains("[7]");
    }

    @Test
    @EnabledOnOs(OS.WINDOWS)
    void noJavaGivesOneSentenceAndExitStatus70OnWindows(@TempDir Path dir) throws Exception {
        Path bin = installation(dir, false);
        Run run = runWithEnv(dir, java.util.Map.of("PATH", "C:\\does-not-exist", "JAVA_HOME", ""), bin.resolve("slay400.cmd").toString());
        assertThat(run.exit()).isEqualTo(70);
        assertThat(run.err()).contains("Java was not found").contains("Java 21 or later");
    }

    @Test
    @EnabledOnOs(OS.WINDOWS)
    void javaOlderThan21GivesOneSentenceAndExitStatus70OnWindows(@TempDir Path dir) throws Exception {
        // The script only ever looks for JAVA_HOME\bin\java.exe (how a real JDK ships on Windows), so the stand-in
        // has to be a real .exe, not a .cmd/.bat the exist check would silently skip, falling through to the real
        // Java 21 on PATH and making this test pass for the wrong reason.
        Path oldJavaHome = dir.resolve("old-java");
        Path oldJavaBin = oldJavaHome.resolve("bin");
        Files.createDirectories(oldJavaBin);
        compileJavaVersionStub(dir, oldJavaBin.resolve("java.exe"), "java version \"1.8.0_392\"");
        Path bin = installation(dir, false);
        Run run = runWithEnv(dir, java.util.Map.of("JAVA_HOME", oldJavaHome.toString()), bin.resolve("slay400.cmd").toString());
        assertThat(run.exit()).isEqualTo(70);
        assertThat(run.err()).contains("Java 21 or later");
    }

    /**
     * Review point 1, on Windows: JAVA_TOOL_OPTIONS or _JAVA_OPTIONS make the JVM print "Picked up ..." as the
     * first line of {@code java -version}, even for an empty value; the script must still find the real version
     * line, not just the first one.
     */
    @Test
    @EnabledOnOs(OS.WINDOWS)
    void javaToolOptionsAndUnderscoreJavaOptionsDoNotBreakVersionDetectionOnWindows(@TempDir Path dir) throws Exception {
        Path bin = installation(dir, false);
        for (String value : List.of("-Xmx128m", "")) {
            Run withToolOptions = runWithEnv(dir, java.util.Map.of("JAVA_TOOL_OPTIONS", value), bin.resolve("slay400.cmd").toString(), "0");
            assertThat(withToolOptions.exit()).as("JAVA_TOOL_OPTIONS=[%s]: %s", value, withToolOptions.err()).isZero();
            Run withJavaOptions = runWithEnv(dir, java.util.Map.of("_JAVA_OPTIONS", value), bin.resolve("slay400.cmd").toString(), "0");
            assertThat(withJavaOptions.exit()).as("_JAVA_OPTIONS=[%s]: %s", value, withJavaOptions.err()).isZero();
        }
    }

    /** The exact reproduction of review point 1, on Windows: an old Java that also picks up JAVA_TOOL_OPTIONS. */
    @Test
    @EnabledOnOs(OS.WINDOWS)
    void javaOlderThan21IsStillDetectedWithAPickedUpToolOptionsLineOnWindows(@TempDir Path dir) throws Exception {
        Path oldJavaHome = dir.resolve("old-java");
        Path oldJavaBin = oldJavaHome.resolve("bin");
        Files.createDirectories(oldJavaBin);
        compileJavaVersionStub(dir, oldJavaBin.resolve("java.exe"), "Picked up JAVA_TOOL_OPTIONS: -Xmx128m", "java version \"1.8.0_392\"");
        Path bin = installation(dir, false);
        Run run = runWithEnv(dir, java.util.Map.of("JAVA_HOME", oldJavaHome.toString(), "JAVA_TOOL_OPTIONS", "-Xmx128m"),
                bin.resolve("slay400.cmd").toString());
        assertThat(run.exit()).isEqualTo(70);
        assertThat(run.err()).contains("Java 21 or later");
    }

    /** Compiles a tiny real .exe (with csc.exe, part of every Windows' .NET Framework) that prints each of {@code lines}. */
    private static void compileJavaVersionStub(Path dir, Path exe, String... lines) throws IOException, InterruptedException {
        Path source = dir.resolve("JavaStub.cs");
        StringBuilder body = new StringBuilder();
        for (String line : lines) {
            body.append("System.Console.Error.WriteLine(\"").append(line.replace("\"", "\\\"")).append("\");");
        }
        Files.writeString(source, "class JavaStub { static void Main() { " + body + " } }\n");
        Path csc = findCsc();
        Process process = new ProcessBuilder(csc.toString(), "/nologo", "/out:" + exe, source.toString())
                .redirectErrorStream(true).start();
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        assertThat(process.waitFor()).as("csc.exe output: %s", output).isZero();
    }

    private static Path findCsc() throws IOException {
        Path framework = Path.of(System.getenv("WINDIR"), "Microsoft.NET", "Framework64");
        try (var versions = Files.list(framework)) {
            return versions.filter(p -> Files.isRegularFile(p.resolve("csc.exe"))).max(Comparator.naturalOrder())
                    .map(p -> p.resolve("csc.exe"))
                    .orElseThrow(() -> new IOException("csc.exe not found under " + framework));
        }
    }

    @Test
    void theScriptsAreTheOnesCommittedToTheRepository() {
        assertThat(POSIX_SCRIPT).isRegularFile();
        assertThat(WINDOWS_SCRIPT).isRegularFile();
        assertThat(List.of(POSIX_SCRIPT, WINDOWS_SCRIPT)).allSatisfy(p -> assertThat(p).isNotEmptyFile());
    }
}
