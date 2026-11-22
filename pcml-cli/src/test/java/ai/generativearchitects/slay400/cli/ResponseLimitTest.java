package ai.generativearchitects.slay400.cli;

import static org.assertj.core.api.Assertions.assertThat;

import ai.generativearchitects.slay400.cli.Support.Result;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * Kickoff 15, Part D (decision 127): an operation whose arrays are each below the large-array threshold, but whose
 * response still multiplies past {@code maxResponseValues}, gets {@code trim} on every fixed array, not only the
 * large ones, so {@code validate} has nothing left to say about the limit -- for an {@code inputoutput} parameter
 * and for an {@code output} one, in the same invented program shape.
 */
class ResponseLimitTest {

    // 25 x 6 x 15 x 20 x 4 char fields = 180,000 values; no array reaches the default threshold of 100.
    private static final String DEEPNEST = """
            <?xml version="1.0"?>
            <pcml version="6.0">
              <struct name="LEAF">
                <data name="A" type="char" length="2"/>
                <data name="B" type="char" length="2"/>
                <data name="C" type="char" length="2"/>
                <data name="D" type="char" length="2"/>
              </struct>
              <struct name="LVL3"><data name="ITEMS" type="struct" struct="LEAF" count="20"/></struct>
              <struct name="LVL2"><data name="ITEMS" type="struct" struct="LVL3" count="15"/></struct>
              <struct name="LVL1"><data name="ITEMS" type="struct" struct="LVL2" count="6"/></struct>
              <program name="DEEPIO" path="/QSYS.LIB/DEMOLIB.LIB/DEEPIO.PGM">
                <data name="DEEP" type="struct" struct="LVL1" count="25" usage="inputoutput"/>
              </program>
              <program name="DEEPOUT" path="/QSYS.LIB/DEMOLIB.LIB/DEEPOUT.PGM">
                <data name="DEEP" type="struct" struct="LVL1" count="25" usage="output"/>
              </program>
            </pcml>
            """;

    private static void initialise(Path dir) {
        Support.write(dir.resolve("apis/DEEPNEST/DEEPNEST.pcml"), DEEPNEST);
        Result init = Support.run(dir, "init");
        assertThat(init.exit()).as(init.err()).isZero();
        assertThat(init.out()).doesNotContain("SCF004");
        String overlay = Support.read(dir.resolve("apis/DEEPNEST/api.yaml"));
        assertThat(overlay).contains("trim:").contains("dropBlank: true")
                .contains("the response of this operation would otherwise always have at least 180000 values, more than the limit of 100000");
    }

    @Test
    void theReproductionAsInputoutputAndAsOutputValidatesWithNoOvl022(@TempDir Path dir) {
        initialise(dir);
        Result annotate = Support.runWithInput(dir, "response\n", "annotate");
        assertThat(annotate.exit()).as(annotate.err()).isZero();
        Result result = Support.run(dir, "validate");
        assertThat(result.out()).doesNotContain("OVL022");
    }

    @Test
    void theReproductionAsInputoutputAndAsOutputValidatesWithNoOvl022WhenAnsweredBoth(@TempDir Path dir) {
        initialise(dir);
        Result annotate = Support.runWithInput(dir, "both\n", "annotate");
        assertThat(annotate.exit()).as(annotate.err()).isZero();
        Result result = Support.run(dir, "validate");
        assertThat(result.out()).doesNotContain("OVL022");
    }
}
