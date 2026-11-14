# Fixed two-rate analytic enclosure argument

This document describes the new policy `alternating32-dyadic128.v1` implemented
in `counterdex/analytical.py`. It establishes interval arithmetic for
one specified analytic template. It does not establish a generic ODE checker,
a model's suitability for an experiment, an instrument's achievable error, or
the truth of the input observations.

## Exponential enclosure

The admitted input is an exact rational `z` with `0 <= z <= 1024`. Its reduced
numerator and positive denominator each have at most 256 bits. Inputs outside
this resource policy fail; precision is never increased automatically.

Repeatedly divide `z` by two until `u = z/2^k <= 1`. At most ten divisions are
required by the admitted range. For `0 <= u <= 1`, the exponential series is

`exp(-u) = sum_{j=0}^infinity (-u)^j/j!`.

The term magnitudes decrease to zero: the ratio from degree `j` to `j+1` is
`u/(j+1) <= 1`. The alternating-series remainder has the sign of its next term
and magnitude at most that term. Consequently the partial sums through degrees
32 and 33 enclose the exact value:

`S33 <= exp(-u) <= S32`.

All terms and partial sums are computed as exact `Fraction` values. For
`D = 2^128`, define `down(q)=floor(D*q)/D` and `up(q)=ceil(D*q)/D`. Exact integer
division implements these directed operations. Thus

`L = max(0, down(S33)) <= exp(-u) <= up(S32) = U`.

The lower truncation is justified only by the mathematical positivity of the
exponential. It is not a numerical underflow heuristic.

Since squaring is monotone on the nonnegative real line,
`L^2 <= exp(-2*u) <= U^2`. Replacing endpoints by `max(0, down(L^2))` and
`up(U^2)` preserves enclosure. Repeat this directed squaring exactly `k` times
to enclose `exp(-z)`. Every returned endpoint is a nonnegative dyadic rational
whose denominator divides `2^128`. At large arguments the lower endpoint can
be zero and the upper endpoint remains positive. No relative-error guarantee
or zero-error claim is attached to this case. `z=0` returns exactly `[1,1]`.

The algorithm has at most 32 Taylor recurrence steps, one additional term,
ten reductions, and ten interval squarings per exponential. The input bit cap
also bounds temporary exact arithmetic: reduction adds at most ten denominator
bits, and Taylor degree is fixed. There is no adaptive solver or imported
numerical package.

## Concentration enclosure and template

The template has `A>0`, `0<ke<ka`, `t>=0`, and

`x(t)=exp(-ka*t)`, `C(t)=A*(exp(-ke*t)-exp(-ka*t))`.

These functions satisfy `x(0)=1`, `C(0)=0`, `x'=-ka*x`, and
`C'=-ke*C+A*(ka-ke)*x` by direct differentiation. The fixed linear system has
a unique solution for these initial values; the explicit analytic functions
are defined for every finite nonnegative time.

If exact exponential enclosures are `[Lke,Uke]` and `[Lka,Uka]`, interval
subtraction and multiplication by positive `A` give

`A*(Lke-Uka) <= C(t) <= A*(Uke-Lka)`.

The implementation preserves a negative lower concentration bound if produced
by conservative subtraction. Each of `A,ke,ka,t`, and each rate/time product
used by the exponential routine, must satisfy its stated bit and range caps.
The concentration result is exact rational arithmetic; its denominator need
not be dyadic because `A` may have a non-dyadic denominator.

## What a caller must still establish

An enclosure does not by itself bind a candidate to a reviewed problem or
verify historical compatibility. A certificate layer must independently bind
the exact parameters, initial conditions, template identity, observations and
their individual hard allowances, approved times and future allowance, and
this precise enclosure policy. It must freshly recompute enclosures rather
than trust stored endpoints or positive flags. Any supported historical
compatibility conclusion requires the entire concentration enclosure at each
included observation to lie inside that observation's permitted interval.
Failure of this sufficient containment test is not proof of incompatibility.

The test suite compares the rational bounds with independent high-precision
`Decimal.exp` values across the admitted range, including close rates and
extreme arguments. Those are diagnostic checks of implementation behavior;
the inequalities above are the soundness argument. Native certificate replay,
browser execution, and environment qualification are separate gates.
