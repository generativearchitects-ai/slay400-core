package ai.generativearchitects.slay400.pcml.codec;

import java.util.List;

/**
 * The number of scalar values a response is guaranteed to hold on every call, assuming every array that carries a
 * trim anywhere on the way down to it shrinks to nothing (the opposite, most favourable case for a response-value
 * limit). Used by {@code OVL022} (kickoff 14, decision 113) and by {@code init}'s own response-limit rule (kickoff
 * 15, Part D, decision 127), which share this one sum rather than each keeping a copy of it: one reads it from an
 * already-built {@link ai.generativearchitects.slay400.pcml.api.FieldBinding} tree (an overlay exists already),
 * the other from a plain PCML field tree with a trim decision of its own in progress (an overlay does not exist
 * yet), so the sum itself is written against a small adapter interface rather than either tree directly.
 */
public final class ResponseValueSum {

    private ResponseValueSum() {
    }

    /** One field of either tree, reduced to what the sum needs to know about it. */
    public interface Field {
        /** False for a field that cannot cost a value at all: not on the response side, hidden, or a count given by
         *  another field at run time (its bound is not known ahead of the call). */
        boolean countsTowardTheLimit();

        /** True when this field's own array, if it is one, already has (or will have) a trim: it then contributes
         *  nothing, the same way {@code countsTowardTheLimit() == false} does. False for a scalar or a struct that
         *  is not itself an array; whether it contributes depends on its children instead. */
        boolean hasTrim();

        /** The declared number of elements if this field is a fixed-size array, {@code -1} otherwise (a scalar, a
         *  struct that is not an array, or a count-by-reference array, counts as one). */
        int fixedCount();

        /** The members of a struct; empty for a scalar. */
        List<Field> children();
    }

    /** The sum over every top-level field of an operation, saturating at {@link Long#MAX_VALUE}. */
    public static long total(List<Field> topLevel) {
        long total = 0;
        for (Field field : topLevel) {
            total = saturatingAdd(total, of(field));
        }
        return total;
    }

    private static long of(Field field) {
        if (!field.countsTowardTheLimit() || field.hasTrim()) {
            return 0;
        }
        long multiplier = field.fixedCount() >= 0 ? field.fixedCount() : 1;
        List<Field> children = field.children();
        if (children.isEmpty()) {
            return multiplier;
        }
        long perElement = 0;
        for (Field child : children) {
            perElement = saturatingAdd(perElement, of(child));
        }
        return saturatingMultiply(multiplier, perElement);
    }

    /** Saturating instead of overflowing, for a declared size deep or wide enough to wrap a {@code long} negative. */
    static long saturatingAdd(long a, long b) {
        try {
            return Math.addExact(a, b);
        } catch (ArithmeticException overflow) {
            return Long.MAX_VALUE;
        }
    }

    static long saturatingMultiply(long a, long b) {
        try {
            return Math.multiplyExact(a, b);
        } catch (ArithmeticException overflow) {
            return Long.MAX_VALUE;
        }
    }
}
