# This package has moved to Counterdex

The scientific library is now **[Counterdex](https://pypi.org/project/counterdex/)**.
This small migration distribution installs `counterdex==0.3.0`; it contains no
separate scientific implementation.

With **CPython 3.11**, install the library directly:

```sh
python3.11 -m pip install counterdex==0.3.0
python3.11 -m counterdex capabilities
```

Use `import counterdex`, `python3.11 -m counterdex`, or the `counterdex` console
command. Update application imports and commands explicitly: this distribution
does **not** provide the former `groundwork_adapter` Python module.

Counterdex 0.3.0 provides bounded candidate discovery, checked counterexamples to
closed parameter claims, separately scoped pair measurement design, follow-up
checks of the original candidate vectors at a reading's own time and hard
allowance, and portable native evidence with fresh offline replay. It has no
runtime dependencies and makes no model-provider or network calls.

The supported model is `C(t) = A * (exp(-ke*t) - exp(-ka*t))`, with `A > 0` and
`0 < ke < ka`. A bounded search finding nothing is inconclusive. Numerical
guidance is not a checked separation guarantee. A follow-up excludes or retains
the named candidates; it does not prove a claim about all possible models.

See the [Counterdex documentation](https://github.com/Arnav-M10/DrBean-hp26/tree/main/packages/groundwork_adapter/docs)
for APIs, exact inputs, scientific limitations and replay contracts.

Existing releases and archived evidence remain historical. Replay requires the
source/runtime recorded in a packet and independently supplied expected anchors;
installing this migration release does not rewrite or upgrade old evidence.
