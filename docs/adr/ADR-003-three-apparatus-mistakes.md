# ADR-003: Three apparatus mistakes, and what replaced them

**Status.** Accepted. The corrections are the most useful thing here, so they are written
down rather than quietly fixed.

## The first: predicting absolute time from the round trip that was requested

E2's apparatus check started as the obvious one. If the cost of an N+1 is its extra round
trips, then the measured difference between the strategies should be the extra query count
times the round trip.

It failed at every setting, and worst at the smallest, where it was out by a factor of
four. Two things were missing.

A short sleep does not last as long as it was asked to. The counter now times what it
actually slept and reports the effective round trip, which at the smallest setting is more
than half as much again as the requested one.

An extra query costs something even when the simulated network costs nothing - parsing,
dispatch, the loopback itself. The sweep measures that directly as the difference at zero
round trip.

With both terms measured, the prediction was much closer and still consistently short, by
a few tenths of a millisecond per query at every setting.

## The second: believing that timing the sleep measured the injection

The residual was the same size at every round trip, which is the signature of a per-query
constant rather than a scaling error.

Injecting delay with a sleep costs more than the sleep. The thread is descheduled, and the
wake-up is paid by whatever runs next - which is the query, not the sleep that caused it.
No amount of timing the sleep more carefully will find that, because by construction it
happens after the sleep has returned.

So the check changed to the claim that survives it: the cost per extra round trip rises
one-for-one with the round trip. The slope is the prediction and is one. The intercept is
the injection overhead, which is real, is measured at an **overhead of 0.33 ms** per query,
and is reported rather than assumed away. The measured slope is **slope of 1.05**.

This is the more honest check as well as the one that passes. The absolute milliseconds
were never going to travel to another machine; the slope is a statement about
serialisation, which does.

## The third: a guessed row width in E3

E3 compares what a join sends against what the batched pair sends, and checks the measured
ratio against the derivation. The derivation needs the width of a parent row and the width
of a child row, and the child width started as a constant guessed from the fixture's shape.

That was fine at wide parents, where the parent term dominates the ratio, and visibly wrong
at narrow ones, where the child term does: at the narrowest width in the sweep the derived
ratio missed the measurement by about a sixth. Both widths are measured from the fixture
now, and the derivation matches at every width.

The guess was not unreasonable and it was unnecessary, which is the point. A quantity that
can be measured in four lines should not be estimated in one.

## What the three have in common

The first was caught by a prediction that failed everywhere. The second by a residual that
did not scale. The third by a disagreement that appeared at one end of a sweep and not the
other - which is almost always a term that matters at one end and not the other, rather
than noise.

None was caught by a test. All three were caught by comparing two things that should have
agreed and taking the gap seriously.
