package ai.generativearchitects.slay400.pcml.model;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Optional;
import org.junit.jupiter.api.Test;

/** {@link WireType#isRawBytes} (kickoff 15, Part A) and {@link WireType#isWholeNumber} (review of PR #21, "to change" #2). */
class WireTypeTest {

    @Test
    void onlyCcsid65535IsRawBytes() {
        assertThat(WireType.isRawBytes(Optional.of(65535))).isTrue();
        assertThat(WireType.isRawBytes(Optional.of(37))).isFalse();
        assertThat(WireType.isRawBytes(Optional.of(65534))).isFalse();
        assertThat(WireType.isRawBytes(Optional.empty())).isFalse();
    }

    @Test
    void intIsAlwaysAWholeNumber() {
        assertThat(WireType.isWholeNumber(new WireType.Int(4, Optional.empty()))).isTrue();
    }

    @Test
    void packedOrZonedIsAWholeNumberOnlyWithNoDecimalPlaces() {
        assertThat(WireType.isWholeNumber(new WireType.Packed(5, 0))).isTrue();
        assertThat(WireType.isWholeNumber(new WireType.Packed(5, 1))).isFalse();
        assertThat(WireType.isWholeNumber(new WireType.Zoned(5, 0))).isTrue();
        assertThat(WireType.isWholeNumber(new WireType.Zoned(5, 2))).isFalse();
    }

    @Test
    void everyOtherWireTypeIsNotAWholeNumber() {
        assertThat(WireType.isWholeNumber(new WireType.Char(new Length.Fixed(3), Optional.empty()))).isFalse();
        assertThat(WireType.isWholeNumber(new WireType.Float(8))).isFalse();
        assertThat(WireType.isWholeNumber(new WireType.Byte(new Length.Fixed(3)))).isFalse();
        assertThat(WireType.isWholeNumber(new WireType.Date())).isFalse();
        assertThat(WireType.isWholeNumber(new WireType.Struct("S"))).isFalse();
    }
}
