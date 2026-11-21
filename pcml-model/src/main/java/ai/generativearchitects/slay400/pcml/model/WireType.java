package ai.generativearchitects.slay400.pcml.model;

import java.util.Objects;
import java.util.Optional;

/**
 * The PCML {@code type} of a {@code data} element, together with the attributes that define how
 * the value is laid out on the wire. Attributes that do not affect the layout (such as
 * {@code dateformat}) stay in the field's attribute map.
 */
public sealed interface WireType {

    /**
     * {@code type="char"}.
     *
     * @param length length in characters
     * @param ccsid  numeric {@code ccsid}, if present and numeric
     */
    record Char(Length length, Optional<Integer> ccsid) implements WireType {
        /** @throws NullPointerException if an argument is {@code null} */
        public Char {
            Objects.requireNonNull(length, "length");
            Objects.requireNonNull(ccsid, "ccsid");
        }
    }

    /**
     * {@code type="varchar"}: a character field preceded by its own length.
     *
     * @param length    maximum length in characters
     * @param varLength size in bytes of the length prefix ({@code varlength}), if present
     * @param ccsid     numeric {@code ccsid}, if present and numeric
     */
    record VarChar(Length length, Optional<Integer> varLength, Optional<Integer> ccsid) implements WireType {
        /** @throws NullPointerException if an argument is {@code null} */
        public VarChar {
            Objects.requireNonNull(length, "length");
            Objects.requireNonNull(varLength, "varLength");
            Objects.requireNonNull(ccsid, "ccsid");
        }
    }

    /**
     * {@code type="int"}.
     *
     * @param lengthBytes size in bytes ({@code length})
     * @param precision   number of significant bits ({@code precision}), if present
     */
    record Int(int lengthBytes, Optional<Integer> precision) implements WireType {
        /** @throws NullPointerException if {@code precision} is {@code null} */
        public Int {
            Objects.requireNonNull(precision, "precision");
        }
    }

    /**
     * {@code type="packed"}.
     *
     * @param length    total number of digits
     * @param precision number of decimal digits
     */
    record Packed(int length, int precision) implements WireType {
    }

    /**
     * {@code type="zoned"}.
     *
     * @param length    total number of digits
     * @param precision number of decimal digits
     */
    record Zoned(int length, int precision) implements WireType {
    }

    /**
     * {@code type="float"}.
     *
     * @param lengthBytes size in bytes ({@code length}): 4 or 8
     */
    record Float(int lengthBytes) implements WireType {
    }

    /**
     * {@code type="byte"}.
     *
     * @param length length in bytes
     */
    record Byte(Length length) implements WireType {
        /** @throws NullPointerException if {@code length} is {@code null} */
        public Byte {
            Objects.requireNonNull(length, "length");
        }
    }

    /**
     * {@code type="struct"}: the field has the layout of a struct, referenced by name. The struct is
     * looked up in {@link PcmlDocument#structs()}; the model does not embed it.
     *
     * @param structName name of the struct, as written in the {@code struct} attribute (for an
     *                   inline nested {@code struct} element, its qualified name, see
     *                   {@link PcmlDocument#structs()})
     */
    record Struct(String structName) implements WireType {
        /**
         * @throws NullPointerException     if {@code structName} is {@code null}
         * @throws IllegalArgumentException if {@code structName} is blank
         */
        public Struct {
            Objects.requireNonNull(structName, "structName");
            if (structName.isBlank()) {
                throw new IllegalArgumentException("structName must not be blank");
            }
        }
    }

    /** {@code type="date"}. Format attributes are kept in the field's attribute map. */
    record Date() implements WireType {
    }

    /** {@code type="time"}. Format attributes are kept in the field's attribute map. */
    record Time() implements WireType {
    }

    /** {@code type="timestamp"}. */
    record Timestamp() implements WireType {
    }

    /**
     * Whether a char or varchar field with this CCSID holds bytes the RPG compiler never converts: CCSID 65535,
     * "not converted". Such a field is {@code byte}-like by default (kickoff 15, Part A).
     */
    static boolean isRawBytes(Optional<Integer> ccsid) {
        return ccsid.isPresent() && ccsid.get() == 65535;
    }

    /**
     * Whether a wire type's value is always a whole number: {@code int}, or {@code packed}/{@code zoned} with no
     * decimal places. A count field of this wire type is read as a whole number whatever its semantic type
     * (kickoff 15, review of PR #21, "to change" #2): a count is often a {@code packed} field with no decimals,
     * which defaults to {@code DECIMAL} like any other packed field.
     */
    static boolean isWholeNumber(WireType wire) {
        return switch (wire) {
            case Int i -> true;
            case Packed p -> p.precision() == 0;
            case Zoned z -> z.precision() == 0;
            default -> false;
        };
    }
}
