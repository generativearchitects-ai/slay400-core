package ai.generativearchitects.slay400.pcml.codec;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * The sum {@code OVL022} and {@code init}'s response-limit rule share (kickoff 14, decision 113; kickoff 15, Part D,
 * decision 127): tested here against a small hand-built tree of {@link ResponseValueSum.Field}, independently of
 * either caller's own adapter (one in {@code pcml-validation}, one in {@code pcml-scaffold}).
 */
class ResponseValueSumTest {

    private static Field leaf() {
        return new Field(true, false, -1, List.of());
    }

    /** A simple, mutable adapter for the tests: a scalar (no children, fixedCount -1), or an array/struct. */
    private record Field(boolean counts, boolean trimmed, int fixedCount, List<ResponseValueSum.Field> children)
            implements ResponseValueSum.Field {
        @Override
        public boolean countsTowardTheLimit() {
            return counts;
        }

        @Override
        public boolean hasTrim() {
            return trimmed;
        }
    }

    @Test
    void aLeafThatCountsContributesOne() {
        assertThat(ResponseValueSum.total(List.of(leaf()))).isEqualTo(1);
    }

    @Test
    void aFieldThatDoesNotCountContributesNothingEvenAsAFixedArray() {
        Field notResponse = new Field(false, false, 50, List.of(leaf()));
        assertThat(ResponseValueSum.total(List.of(notResponse))).isZero();
    }

    @Test
    void aTrimmedArrayContributesNothingEvenWithChildren() {
        Field trimmed = new Field(true, true, 50, List.of(leaf(), leaf()));
        assertThat(ResponseValueSum.total(List.of(trimmed))).isZero();
    }

    @Test
    void aFixedArrayOfScalarsMultipliesItsDeclaredSize() {
        Field array = new Field(true, false, 5, List.of(leaf()));
        assertThat(ResponseValueSum.total(List.of(array))).isEqualTo(5);
    }

    @Test
    void nestingMultipliesThroughEachLevel() {
        // An array of 3 structs, each with 2 scalars: 3 * 2 = 6.
        Field struct = new Field(true, false, -1, List.of(leaf(), leaf()));
        Field array = new Field(true, false, 3, List.of(struct));
        assertThat(ResponseValueSum.total(List.of(array))).isEqualTo(6);
    }

    @Test
    void severalTopLevelFieldsAreSummed() {
        assertThat(ResponseValueSum.total(List.of(leaf(), leaf(), new Field(true, false, 4, List.of(leaf()))))).isEqualTo(6);
    }

    @Test
    void theSumSaturatesInsteadOfOverflowing() {
        // Three nested arrays of Integer.MAX_VALUE elements each: the product is far beyond Long.MAX_VALUE.
        Field level3 = new Field(true, false, Integer.MAX_VALUE, List.of(leaf()));
        Field level2 = new Field(true, false, Integer.MAX_VALUE, List.of(level3));
        Field level1 = new Field(true, false, Integer.MAX_VALUE, List.of(level2));
        assertThat(ResponseValueSum.total(List.of(level1))).isEqualTo(Long.MAX_VALUE);
    }

    @Test
    void saturatingAddAndMultiplyWrapAtTheirBoundary() {
        assertThat(ResponseValueSum.saturatingAdd(1, 2)).isEqualTo(3);
        assertThat(ResponseValueSum.saturatingAdd(Long.MAX_VALUE, 1)).isEqualTo(Long.MAX_VALUE);
        assertThat(ResponseValueSum.saturatingMultiply(3, 4)).isEqualTo(12);
        assertThat(ResponseValueSum.saturatingMultiply(Long.MAX_VALUE, 2)).isEqualTo(Long.MAX_VALUE);
    }
}
