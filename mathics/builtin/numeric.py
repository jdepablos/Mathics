#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Numeric evaluation

Support for numeric evaluation with arbitrary precision is just a proof-of-concept.
Precision is not "guarded" through the evaluation process. Only integer precision is supported.
However, things like 'N[Pi, 100]' should work as expected.
"""

from __future__ import unicode_literals
from __future__ import absolute_import

import sympy
import hashlib
import zlib
from six.moves import range

from mathics.builtin.base import Builtin, Predefined
from mathics.core.numbers import (dps, prec,
                                  convert_int_to_digit_list)
from mathics.core.expression import (
    Integer, Rational, Real, Complex, Expression, Number, Symbol, from_python,
    MachineReal, PrecisionReal)
from mathics.core.convert import from_sympy
from mathics.core.numbers import machine_precision


class N(Builtin):
    """
    <dl>
    <dt>'N[$expr$, $prec$]'
        <dd>evaluates $expr$ numerically with a precision of $prec$ digits.
    </dl>
    >> N[Pi, 50]
     = 3.1415926535897932384626433832795028841971693993751

    >> N[1/7]
     = 0.142857

    >> N[1/7, 5]
     = 0.14286

    You can manually assign numerical values to symbols.
    When you do not specify a precision, 'MachinePrecision' is taken.
    >> N[a] = 10.9
     = 10.9
    >> a
     = a

    'N' automatically threads over expressions, except when a symbol has attributes 'NHoldAll', 'NHoldFirst', or 'NHoldRest'.
    >> N[a + b]
     = 10.9 + b
    >> N[a, 20]
     = a
    >> N[a, 20] = 11;
    >> N[a + b, 20]
     = 11. + b
    >> N[f[a, b]]
     = f[10.9, b]
    >> SetAttributes[f, NHoldAll]
    >> N[f[a, b]]
     = f[a, b]

    The precision can be a pattern:
    >> N[c, p_?(#>10&)] := p
    >> N[c, 3]
     = c
    >> N[c, 11]
     = 11.

    You can also use 'UpSet' or 'TagSet' to specify values for 'N':
    >> N[d] ^= 5;
    However, the value will not be stored in 'UpValues', but in 'NValues' (as for 'Set'):
    >> UpValues[d]
     = {}
    >> NValues[d]
     = {HoldPattern[N[d, MachinePrecision]] :> 5}
    >> e /: N[e] = 6;
    >> N[e]
     = 6.

    Values for 'N[$expr$]' must be associated with the head of $expr$:
    >> f /: N[e[f]] = 7;
     : Tag f not found or too deep for an assigned rule.

    You can use 'Condition':
    >> N[g[x_, y_], p_] := x + y * Pi /; x + y > 3
    >> SetAttributes[g, NHoldRest]
    >> N[g[1, 1]]
     = g[1., 1]
    >> N[g[2, 2]] // InputForm
     = 8.283185307179586

    #> p=N[Pi,100]
     = 3.141592653589793238462643383279502884197169399375105820974944592307816406286208998628034825342117068
    #> ToString[p]
     = 3.141592653589793238462643383279502884197169399375105820974944592307816406286208998628034825342117068
    #> 3.14159 * "a string"
     = 3.14159 a string

    #> N[Pi, Pi]
     = 3.14

    #> N[1/9, 30]
     = 0.111111111111111111111111111111
    #> Precision[%]
     = 30.

    #> N[1.5, 30]
     = 1.5
    #> Precision[%]
     = MachinePrecision
    #> N[1.5, 5]
     = 1.5
    #> Precision[%]
     = MachinePrecision

    #> {N[x], N[x, 30], N["abc"], N["abc", 30]}
     = {x, x, abc, abc}
    """

    messages = {
        'precbd': (
            "Requested precision `1` is not a machine-sized real number."),
    }

    rules = {
        'N[expr_]': 'N[expr, MachinePrecision]',
    }

    def apply_other(self, expr, prec, evaluation):
        'N[expr_, prec_]'

        if prec.get_name() == 'System`MachinePrecision':
            d = None
        else:
            d = prec.get_float_value(n_evaluation=evaluation)
            if d is None:
                return evaluation.message('N', 'precbd', prec)

        if expr.get_head_name() in ('System`List', 'System`Rule'):
            return Expression(
                expr.head, *[self.apply_other(leaf, prec, evaluation)
                             for leaf in expr.leaves])

        if isinstance(expr, MachineReal):
            return expr
        if isinstance(expr, Number):
            return expr.round(d)

        name = expr.get_lookup_name()
        if name != '':
            nexpr = Expression('N', expr, prec)
            result = evaluation.definitions.get_value(
                name, 'System`NValues', nexpr, evaluation)
            if result is not None:
                if not result.same(nexpr):
                    result = Expression(
                        'N', result, prec).evaluate(evaluation)
                return result

        if expr.is_atom():
            return expr
        else:
            attributes = expr.head.get_attributes(evaluation.definitions)
            if 'System`NHoldAll' in attributes:
                eval_range = ()
            elif 'System`NHoldFirst' in attributes:
                eval_range = range(1, len(expr.leaves))
            elif 'System`NHoldRest' in attributes:
                if len(expr.leaves) > 0:
                    eval_range = (0,)
                else:
                    eval_range = ()
            else:
                eval_range = range(len(expr.leaves))
            head = Expression('N', expr.head, prec).evaluate(evaluation)
            leaves = expr.leaves[:]
            for index in eval_range:
                leaves[index] = Expression(
                    'N', leaves[index], prec).evaluate(evaluation)
            return Expression(head, *leaves)


class MachinePrecision(Predefined):
    """
    <dl>
    <dt>'MachinePrecision'
        <dd>is a "pessimistic" (integer) estimation of the internally used standard precision.
    </dl>
    >> N[MachinePrecision]
     = 18.
    """

    def apply_N(self, prec, evaluation):
        'N[MachinePrecision, prec_]'

        prec = get_precision(prec, evaluation)
        if prec is not None:
            return Real(dps(machine_precision), prec)


class Precision(Builtin):
    """
    <dl>
    <dt>'Precision[$expr$]'
        <dd>examines the number of significant digits of $expr$.
    </dl>
    This is rather a proof-of-concept than a full implementation. Precision of
    compound expression is not supported yet.
    >> Precision[1]
     = Infinity
    >> Precision[1/2]
     = Infinity
    >> Precision[0.5]
     = MachinePrecision

    #> Precision[0.0]
     = MachinePrecision
    #> Precision[0.000000000000000000000000000000000000]
     = 0.
    #> Precision[-0.0]
     = MachinePrecision
    #> Precision[-0.000000000000000000000000000000000000]
     = 0.

    #> 1.0000000000000000 // Precision
     = MachinePrecision
    #> 1.00000000000000000 // Precision
     = 17.

    #> 0.4 + 2.4 I // Precision
     = MachinePrecision
    #> Precision[2 + 3 I]
     = Infinity

    #> Precision["abc"]
     = Infinity
    """

    rules = {
        'Precision[z_?MachineNumberQ]': 'MachinePrecision',
    }

    def apply(self, z, evaluation):
        'Precision[z_]'

        if not z.is_inexact():
            return Symbol('Infinity')
        elif z.to_sympy().is_zero:
            return Real(0)
        else:
            return Real(dps(z.get_precision()))


def round(value, k):
    n = (1. * value / k).as_real_imag()[0]
    if n >= 0:
        n = sympy.Integer(n + 0.5)
    else:
        n = sympy.Integer(n - 0.5)
    return n * k


class Round(Builtin):
    """
    <dl>
    <dt>'Round[$expr$]'
        <dd>rounds $expr$ to the nearest integer.
    <dt>'Round[$expr$, $k$]'
        <dd>rounds $expr$ to the closest multiple of $k$.
    </dl>

    >> Round[10.6]
     = 11
    >> Round[0.06, 0.1]
     = 0.1
    ## This should return 0. but doesn't due to a bug in sympy
    >> Round[0.04, 0.1]
     = 0

    Constants can be rounded too
    >> Round[Pi, .5]
     = 3.
    >> Round[Pi^2]
     = 10

    Round to exact value
    >> Round[2.6, 1/3]
     = 8 / 3
    >> Round[10, Pi]
     = 3 Pi

    Round complex numbers
    >> Round[6/(2 + 3 I)]
     = 1 - I
    >> Round[1 + 2 I, 2 I]
     = 2 I

    Round Negative numbers too
    >> Round[-1.4]
     = -1

    Expressions other than numbers remain unevaluated:
    >> Round[x]
     = Round[x]
    >> Round[1.5, k]
     = Round[1.5, k]
    """

    attributes = ('Listable', 'NumericFunction')

    rules = {
        'Round[expr_?NumericQ]': 'Round[Re[expr], 1] + I * Round[Im[expr], 1]',
        'Round[expr_Complex, k_RealNumberQ]': (
            'Round[Re[expr], k] + I * Round[Im[expr], k]'),
    }

    def apply(self, expr, k, evaluation):
        "Round[expr_?NumericQ, k_?NumericQ]"
        return from_sympy(round(expr.to_sympy(), k.to_sympy()))


def chop(expr, delta=10.0 ** (-10.0)):
    if isinstance(expr, Real):
        if -delta < expr.to_python() < delta:
            return Integer(0)
    elif isinstance(expr, Complex):
        real, imag = expr.real, expr.imag
        if -delta < real.to_python() < delta:
            real = Integer(0)
        if -delta < imag.to_python() < delta:
            imag = Integer(0)
        return Complex(real, imag)
    elif isinstance(expr, Expression):
        return Expression(chop(expr.head), *[
            chop(leaf) for leaf in expr.leaves])
    return expr


class Chop(Builtin):
    """
    <dl>
    <dt>'Chop[$expr$]'
        <dd>replaces floating point numbers close to 0 by 0.
    <dt>'Chop[$expr$, $delta$]'
        <dd>uses a tolerance of $delta$. The default tolerance is '10^-10'.
    </dl>

    >> Chop[10.0 ^ -16]
     = 0
    >> Chop[10.0 ^ -9]
     = 1.*^-9
    >> Chop[10 ^ -11 I]
     = I / 100000000000
    >> Chop[0. + 10 ^ -11 I]
     = 0
    """

    messages = {
        'tolnn': "Tolerance specification a must be a non-negative number.",
    }

    rules = {
        'Chop[expr_]': 'Chop[expr, 10^-10]',
    }

    def apply(self, expr, delta, evaluation):
        'Chop[expr_, delta_:(10^-10)]'

        delta = delta.evaluate(evaluation).get_float_value()
        if delta is None or delta < 0:
            return evaluation.message('Chop', 'tolnn')

        return chop(expr, delta=delta)


class NumericQ(Builtin):
    """
    <dl>
    <dt>'NumericQ[$expr$]'
        <dd>tests whether $expr$ represents a numeric quantity.
    </dl>

    >> NumericQ[2]
     = True
    >> NumericQ[Sqrt[Pi]]
     = True
    >> NumberQ[Sqrt[Pi]]
     = False
    """

    def apply(self, expr, evaluation):
        'NumericQ[expr_]'

        def test(expr):
            if isinstance(expr, Expression):
                attr = evaluation.definitions.get_attributes(
                    expr.head.get_name())
                return 'System`NumericFunction' in attr and all(
                    test(leaf) for leaf in expr.leaves)
            else:
                return expr.is_numeric()

        return Symbol('True') if test(expr) else Symbol('False')


class RealValuedNumericQ(Builtin):
    '''
    #> Internal`RealValuedNumericQ /@ {1, N[Pi], 1/2, Sin[1.], Pi, 3/4, aa,  I}
     = {True, True, True, True, True, True, False, False}
    '''

    context = 'Internal`'

    rules = {
        'Internal`RealValuedNumericQ[x_]': 'Head[N[x]] === Real',
    }


class RealValuedNumberQ(Builtin):
    '''
    #>  Internal`RealValuedNumberQ /@ {1, N[Pi], 1/2, Sin[1.], Pi, 3/4, aa, I}
     = {True, True, True, True, False, True, False, False}
    '''

    context = 'Internal`'

    rules = {
        'Internal`RealValuedNumberQ[x_Real]': 'True',
        'Internal`RealValuedNumberQ[x_Integer]': 'True',
        'Internal`RealValuedNumberQ[x_Rational]': 'True',
        'Internal`RealValuedNumberQ[x_]': 'False',
    }


class IntegerDigits(Builtin):
    """
    <dl>
    <dt>'IntegerDigits[$n$]'
        <dd>returns a list of the base-10 digits in the integer $n$.
    <dt>'IntegerDigits[$n$, $base$]'
        <dd>returns a list of the base-$base$ digits in $n$.
    <dt>'IntegerDigits[$n$, $base$, $length$]'
        <dd>returns a list of length $length$, truncating or padding
        with zeroes on the left as necessary.
    </dl>

    >> IntegerDigits[76543]
     = {7, 6, 5, 4, 3}

    The sign of $n$ is discarded:
    >> IntegerDigits[-76543]
     = {7, 6, 5, 4, 3}

    >> IntegerDigits[15, 16]
     = {15}
    >> IntegerDigits[1234, 16]
     = {4, 13, 2}
    >> IntegerDigits[1234, 10, 5]
     = {0, 1, 2, 3, 4}

    #> IntegerDigits[1000, 10]
     = {1, 0, 0, 0}

    #> IntegerDigits[0]
     = {0}
    """

    attributes = ('Listable',)

    messages = {
        'int': 'Integer expected at position 1 in `1`',
        'ibase': 'Base `1` is not an integer greater than 1.',
    }

    rules = {
        'IntegerDigits[n_]': 'IntegerDigits[n, 10]',
    }

    def apply_len(self, n, base, length, evaluation):
        'IntegerDigits[n_, base_, length_]'

        if not(isinstance(length, Integer) and length.get_int_value() >= 0):
            return evaluation.message('IntegerDigits', 'intnn')

        return self.apply(n, base, evaluation,
                          nr_elements=length.get_int_value())

    def apply(self, n, base, evaluation, nr_elements=None):
        'IntegerDigits[n_, base_]'

        if not(isinstance(n, Integer)):
            return evaluation.message('IntegerDigits', 'int',
                                      Expression('IntegerDigits', n, base))

        if not(isinstance(base, Integer) and base.get_int_value() > 1):
            return evaluation.message('IntegerDigits', 'ibase', base)

        if nr_elements == 0:
            # trivial case: we don't want any digits
            return Expression('List')

        digits = convert_int_to_digit_list(
            n.get_int_value(), base.get_int_value())

        if nr_elements is not None:
            if len(digits) >= nr_elements:
                # Truncate, preserving the digits on the right
                digits = digits[-nr_elements:]
            else:
                # Pad with zeroes
                digits = [0] * (nr_elements - len(digits)) + digits

        return Expression('List', *digits)


class _ZLibHash:  # make zlib hashes behave as if they were from hashlib
    def __init__(self, fn):
        self._bytes = b''
        self._fn = fn

    def update(self, bytes):
        self._bytes += bytes

    def hexdigest(self):
        return format(self._fn(self._bytes), 'x')


class Hash(Builtin):
    """
    <dl>
    <dt>'Hash[$expr$]'
      <dd>returns an integer hash for the given $expr$.
    <dt>'Hash[$expr$, $type$]'
      <dd>returns an integer hash of the specified $type$ for the given $expr$.</dd>
      <dd>The types supported are "MD5", "Adler32", "CRC32", "SHA", "SHA224", "SHA256", "SHA384", and "SHA512".</dd>
    </dl>

    > Hash["The Adventures of Huckleberry Finn"]
    = 213425047836523694663619736686226550816

    > Hash["The Adventures of Huckleberry Finn", "SHA256"]
    = 95092649594590384288057183408609254918934351811669818342876362244564858646638

    > Hash[1/3]
    = 56073172797010645108327809727054836008

    > Hash[{a, b, {c, {d, e, f}}}]
    = 135682164776235407777080772547528225284

    > Hash[SomeHead[3.1415]]
    = 58042316473471877315442015469706095084

    >> Hash[{a, b, c}, "xyzstr"]
     = Hash[{a, b, c}, xyzstr]
    """

    rules = {
        'Hash[expr_]': 'Hash[expr, "MD5"]',
    }

    attributes = ('Protected', 'ReadProtected')

    # FIXME md2
    _supported_hashes = {
        'Adler32': lambda: _ZLibHash(zlib.adler32),
        'CRC32': lambda: _ZLibHash(zlib.crc32),
        'MD5': hashlib.md5,
        'SHA': hashlib.sha1,
        'SHA224': hashlib.sha224,
        'SHA256': hashlib.sha256,
        'SHA384': hashlib.sha384,
        'SHA512': hashlib.sha512,
    }

    @staticmethod
    def compute(user_hash, py_hashtype):
        hash_func = Hash._supported_hashes.get(py_hashtype)
        if hash_func is None:  # unknown hash function?
            return  # in order to return original Expression
        h = hash_func()
        user_hash(h.update)
        return from_python(int(h.hexdigest(), 16))

    def apply(self, expr, hashtype, evaluation):
        'Hash[expr_, hashtype_String]'
        return Hash.compute(expr.user_hash, hashtype.get_string_value())
