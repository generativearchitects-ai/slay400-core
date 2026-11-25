package ai.generativearchitects.slay400.cli;

import static org.assertj.core.api.Assertions.assertThat;

import ai.generativearchitects.slay400.cli.Support.Result;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.EnumSet;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;
import org.junit.jupiter.api.io.TempDir;

/**
 * Kickoff 17, decision 147: {@code gateway} runs {@code slay400-gateway}, found on PATH, with the given arguments,
 * passing standard input, output and error through and returning its exit status; the generator has no dependency
 * on the gateway and does not install it.
 */
class GatewayCommandTest {

    @Test
    void whenNotOnPathItSaysSoAndReturnsGatewayNotFound(@TempDir Path dir) throws IOException {
        Path empty = dir.resolve("empty");
        Files.createDirectories(empty);
        Result result = Support.runOnPath(dir, empty.toString(), "gateway", "run");
        assertThat(result.exit()).isEqualTo(Cli.GATEWAY_NOT_FOUND);
        assertThat(result.out()).isEmpty();
        assertThat(result.err()).contains("slay400-gateway was not found on PATH")
                .contains("https://github.com/generativearchitects-ai/slay400");
    }

    @Test
    void anEmptyOrMissingPathFindsNothingEither(@TempDir Path dir) {
        assertThat(Support.runOnPath(dir, "", "gateway").exit()).isEqualTo(Cli.GATEWAY_NOT_FOUND);
        assertThat(Support.runOnPath(dir, null, "gateway").exit()).isEqualTo(Cli.GATEWAY_NOT_FOUND);
    }

    @Test
    @EnabledOnOs({OS.LINUX, OS.MAC})
    void onPosixItForwardsArgumentsAndStandardStreamsAndReturnsTheStubsExitStatus(@TempDir Path dir) throws IOException {
        Path bin = stubPosix(dir, "echo \"out: $1 $2\"\necho \"err: $(cat)\" >&2\nexit 7");
        Result result = Support.runWithInputOnPath(dir, bin.toString(), "hello\n", "gateway", "run", "check");
        assertThat(result.exit()).isEqualTo(7);
        assertThat(result.out()).isEqualTo("out: run check\n");
        assertThat(result.err()).isEqualTo("err: hello\n");
    }

    @Test
    @EnabledOnOs({OS.LINUX, OS.MAC})
    void onPosixTheFirstFolderOnThePathThatHasItWins(@TempDir Path dir) throws IOException {
        Path first = stubPosix(dir.resolve("1"), "exit 1");
        Path second = stubPosix(dir.resolve("2"), "exit 2");
        Result result = Support.runOnPath(dir, first + ":" + second, "gateway");
        assertThat(result.exit()).isEqualTo(1);
    }

    @Test
    @EnabledOnOs({OS.LINUX, OS.MAC})
    void onPosixOnlyTheBareNameIsTriedEvenWhenAnExecutableCmdFileSitsBeside(@TempDir Path dir) throws IOException {
        Path bin = stubPosix(dir, "exit 3");
        Path decoy = bin.resolve("slay400-gateway.cmd");
        Files.writeString(decoy, "#!/bin/sh\nexit 9\n");
        Files.setPosixFilePermissions(decoy, EnumSet.of(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE,
                PosixFilePermission.OWNER_EXECUTE));
        Result result = Support.runOnPath(dir, bin.toString(), "gateway");
        assertThat(result.exit()).isEqualTo(3);
    }

    @Test
    @EnabledOnOs(OS.WINDOWS)
    void onWindowsItForwardsArgumentsAndReturnsTheStubsExitStatus(@TempDir Path dir) throws IOException {
        Path bin = dir.resolve("bin");
        Files.createDirectories(bin);
        Files.writeString(bin.resolve("slay400-gateway.cmd"), "@echo off\r\necho out: %1 %2\r\nexit /b 7\r\n");
        Result result = Support.runOnPath(dir, bin.toString(), "gateway", "run", "check");
        assertThat(result.exit()).isEqualTo(7);
        assertThat(result.out()).isEqualTo("out: run check\r\n");
    }

    private static Path stubPosix(Path dir, String body) throws IOException {
        Path bin = dir.resolve("bin");
        Files.createDirectories(bin);
        Path script = bin.resolve("slay400-gateway");
        Files.writeString(script, "#!/bin/sh\n" + body + "\n");
        Files.setPosixFilePermissions(script, EnumSet.of(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE,
                PosixFilePermission.OWNER_EXECUTE));
        return bin;
    }
}
