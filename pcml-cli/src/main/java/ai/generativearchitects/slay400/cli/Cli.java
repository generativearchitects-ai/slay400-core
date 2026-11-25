package ai.generativearchitects.slay400.cli;

import ai.generativearchitects.slay400.emit.descriptor.Tool;
import ai.generativearchitects.slay400.pcml.diagnostics.Diagnostic;
import ai.generativearchitects.slay400.pcml.model.SourceLocation;
import ai.generativearchitects.slay400.report.JsonReport;
import ai.generativearchitects.slay400.report.Report;
import ai.generativearchitects.slay400.report.SarifReport;
import ai.generativearchitects.slay400.report.TextReport;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * The command line, as a function: arguments in, exit code out. It never exits the process and reads no environment
 * variable other than {@code PATH} (passed in explicitly, to find {@code slay400-gateway}; the five-argument
 * overload of {@link #run} reads the real one as a convenience). Only {@code annotate} reads the input stream,
 * except {@code gateway}, which also passes it through to the gateway. The report goes to the output stream or to
 * the report file; everything else, usage, progress and the files written, goes to the error stream, so that the
 * output of a JSON or SARIF report is one document and nothing else.
 */
public final class Cli {

    /** Completed, and nothing at or above {@code --fail-on}. */
    public static final int OK = 0;
    /** Diagnostics at or above {@code --fail-on}. */
    public static final int FAILED = 1;
    /** A command line that cannot be run. */
    public static final int USAGE = 2;
    /** An unexpected failure. */
    public static final int UNEXPECTED = 3;
    /** {@code gateway}: {@code slay400-gateway} was not found on {@code PATH} (kickoff 17, decision 147). */
    public static final int GATEWAY_NOT_FOUND = 4;

    private static final String GATEWAY_COMMAND = "slay400-gateway";
    private static final String GATEWAY_REPOSITORY_URL = "https://github.com/generativearchitects-ai/slay400";

    private static final Map<String, Command> COMMANDS = Map.of("init", new InitCommand(), "annotate", new AnnotateCommand(),
            "validate", new ValidateCommand(), "generate", new GenerateCommand(), "bundle", new BundleCommand(),
            "diff", new DiffCommand());

    private Cli() {
    }

    /**
     * Runs a command line, finding {@code slay400-gateway} on the real {@code PATH} environment variable.
     *
     * @param args             the arguments
     * @param workingDirectory what relative paths are relative to
     * @param in               what {@code annotate} reads the answers from, one per line, and what {@code gateway} passes through
     * @param out              where the report, or the help and the version, are written
     * @param err              where everything else is written
     * @return the exit code
     */
    public static int run(String[] args, Path workingDirectory, InputStream in, PrintStream out, PrintStream err) {
        return run(args, workingDirectory, in, out, err, System.getenv("PATH"));
    }

    /**
     * Runs a command line.
     *
     * @param args             the arguments
     * @param workingDirectory what relative paths are relative to
     * @param in               what {@code annotate} reads the answers from, one per line, and what {@code gateway} passes through
     * @param out              where the report, or the help and the version, are written
     * @param err              where everything else is written
     * @param path             where {@code gateway} looks for {@code slay400-gateway}: {@code PATH}-style, entries separated by
     *                         {@link File#pathSeparator}; {@code null} or empty finds nothing
     * @return the exit code
     */
    public static int run(String[] args, Path workingDirectory, InputStream in, PrintStream out, PrintStream err, String path) {
        Objects.requireNonNull(args, "args");
        Objects.requireNonNull(workingDirectory, "workingDirectory");
        Objects.requireNonNull(in, "in");
        Objects.requireNonNull(out, "out");
        Objects.requireNonNull(err, "err");
        boolean stacktrace = List.of(args).contains("--stacktrace");
        try {
            return dispatch(List.of(args), workingDirectory, in, out, err, path);
        } catch (UsageException e) {
            err.println(Tool.NAME + ": " + e.getMessage() + ". Try '" + Tool.NAME + " --help'.");
            return USAGE;
        } catch (Exception | StackOverflowError | OutOfMemoryError e) {
            err.println(Tool.NAME + ": unexpected failure: " + e.getClass().getName() + ": " + TextReport.escape(String.valueOf(e.getMessage())));
            if (stacktrace) {
                e.printStackTrace(err);
            }
            return UNEXPECTED;
        }
    }

    private static int dispatch(List<String> args, Path workingDirectory, InputStream in, PrintStream out, PrintStream err, String path)
            throws Exception {
        if (args.isEmpty()) {
            print(out, Help.general());
            return OK;
        }
        String first = args.get(0);
        if (first.equals("--help") || first.equals("help") && args.size() == 1) {
            print(out, Help.general());
            return OK;
        }
        if (first.equals("--version") || first.equals("version")) {
            print(out, Tool.NAME + " " + Tool.version() + "\n");
            return OK;
        }
        if (first.equals("help")) {
            if (args.size() > 2) {
                throw new UsageException("Unexpected argument '" + Options.shown(args.get(2)) + "'");
            }
            String sub = args.get(1);
            if (!Options.COMMANDS.contains(sub) && !sub.equals("gateway")) {
                throw new UsageException("Unknown command '" + Options.shown(sub) + "'");
            }
            print(out, Help.of(sub));
            return OK;
        }
        if (first.equals("gateway")) {
            return runGateway(args.subList(1, args.size()), path, in, out, err);
        }
        if (!Options.COMMANDS.contains(first)) {
            throw new UsageException(first.startsWith("-") ? "Unknown option '" + Options.shown(first) + "'"
                    : "Unknown command '" + Options.shown(first) + "'");
        }
        Options options = Options.parse(first, args.subList(1, args.size()));
        if (options.help()) {
            print(out, Help.of(first));
            return OK;
        }
        Context context = new Context(options, workingDirectory, in, out, err);
        COMMANDS.get(first).run(context);
        return finish(context, first);
    }

    /**
     * {@code gateway}: finds {@code slay400-gateway} on {@code path} and runs it with {@code arguments}, passing
     * {@code in}, {@code out} and {@code err} through untouched and returning its exit status. The generator has no
     * dependency on the gateway and does not install it (licence boundary, decision 147): when it is not found, says
     * so in one sentence, with where its documentation is, and returns {@link #GATEWAY_NOT_FOUND}.
     */
    private static int runGateway(List<String> arguments, String path, InputStream in, PrintStream out, PrintStream err)
            throws IOException, InterruptedException {
        Optional<Path> found = findOnPath(GATEWAY_COMMAND, path);
        if (found.isEmpty()) {
            err.println(Tool.NAME + ": " + GATEWAY_COMMAND + " was not found on PATH. The gateway is installed separately; see "
                    + GATEWAY_REPOSITORY_URL + " for its documentation.");
            return GATEWAY_NOT_FOUND;
        }
        List<String> command = new ArrayList<>();
        command.add(found.get().toString());
        command.addAll(arguments);
        Process process = new ProcessBuilder(command).start();
        Thread input = pump(in, process.getOutputStream(), true);
        Thread output = pump(process.getInputStream(), out, false);
        Thread error = pump(process.getErrorStream(), err, false);
        int exit = process.waitFor();
        output.join();
        error.join();
        out.flush();
        err.flush();
        input.interrupt();
        return exit;
    }

    /** Copies bytes on a daemon thread until {@code from} ends; closes {@code to} then if {@code closeOnEnd}. */
    private static Thread pump(InputStream from, OutputStream to, boolean closeOnEnd) {
        Thread thread = new Thread(() -> {
            try {
                from.transferTo(to);
            } catch (IOException ignored) {
                // the process ended, or one of the streams closed
            } finally {
                if (closeOnEnd) {
                    try {
                        to.close();
                    } catch (IOException ignored) {
                        // nothing left to do with a stream that will not close
                    }
                }
            }
        });
        thread.setDaemon(true);
        thread.start();
        return thread;
    }

    /** The names {@code name} may be installed under, most specific first, for the running platform. */
    private static List<String> candidateNames(String name) {
        String os = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
        return os.contains("win") ? List.of(name + ".cmd", name + ".exe", name + ".bat", name) : List.of(name);
    }

    /** The first executable file named one of {@code name}'s platform candidates in one of {@code path}'s folders. */
    private static Optional<Path> findOnPath(String name, String path) {
        if (path == null || path.isEmpty()) {
            return Optional.empty();
        }
        for (String folder : path.split(File.pathSeparator, -1)) {
            if (folder.isEmpty()) {
                continue;
            }
            for (String candidate : candidateNames(name)) {
                Path file = Path.of(folder, candidate);
                if (Files.isRegularFile(file) && Files.isExecutable(file)) {
                    return Optional.of(file);
                }
            }
        }
        return Optional.empty();
    }

    /** Writes the report and decides the exit code. */
    private static int finish(Context context, String command) {
        Report report = new Report(command, context.repo, context.diagnostics);
        String text = switch (context.options.format()) {
            case "json" -> JsonReport.render(report);
            case "sarif" -> SarifReport.render(report);
            default -> TextReport.render(report);
        };
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (context.options.value("--report").isPresent()) {
            Path file = context.workingDirectory.resolve(context.options.value("--report").get()).toAbsolutePath().normalize();
            try {
                Files.createDirectories(file.getParent());
                Files.write(file, bytes);
            } catch (IOException e) {
                Diagnostic d = new Diagnostic("CLI003", ai.generativearchitects.slay400.pcml.diagnostics.Severity.ERROR,
                        "The report file " + context.shown(file) + " could not be written: " + Writing.reason(e), new SourceLocation(context.shown(file), 1, 1));
                context.err.print(TextReport.render(new Report(command, context.repo, List.of(d))));
                return FAILED;
            }
            context.err.println("report written to " + context.shown(file));
        } else {
            context.out.write(bytes, 0, bytes.length);
            context.out.flush();
        }
        boolean fails = context.diagnostics.stream().anyMatch(d -> d.severity().ordinal() <= context.options.failOn().ordinal());
        return fails || context.hasError() ? FAILED : OK;
    }

    private static void print(PrintStream out, String text) {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        out.write(bytes, 0, bytes.length);
        out.flush();
    }
}
