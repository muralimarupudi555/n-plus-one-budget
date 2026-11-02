# ADR-002: Simulating distance with a sleep

**Status.** Accepted.

## The decision

Network distance is simulated by sleeping before each query, inside the counting cursor.
There is no second machine, no traffic shaping and no container network.

## Why that is the right shape

The thing that makes an N+1 expensive is that each query waits for the previous one to come
back. The application sends, blocks, receives, and only then decides to send the next one.
That serialisation is the mechanism, and a sleep reproduces it exactly: `n` queries become
`n` waits that cannot overlap, which is the same arithmetic a real network produces.

What a sleep does not reproduce is everything else about a network - bandwidth limits,
congestion, packet loss, the kernel's buffering, TLS. None of those change the count of
round trips, which is what the measurement is about, and all of them would add variance
that has nothing to do with the finding.

Running against a database on another host would be more realistic and much less useful.
The round trip would be whatever that link happened to be, unrepeatable, and impossible to
sweep. Here it is a parameter, which is what lets E2 show the same code at six distances
in one run.

## Why the sleep is timed

Because it does not last as long as it is asked to. At a tenth of a millisecond the
scheduler adds more than half as much again, so a prediction built on the requested figure
is wrong by a factor that the sweep would otherwise report as a finding. The counter times
what it actually slept and reports the effective round trip.

That was not enough on its own, and ADR-003 describes the rest: injecting delay with a
sleep costs more than the sleep, because the thread is descheduled and the wake-up is paid
by whatever runs next. The honest response was to stop predicting absolute times and check
the slope instead.

## What the numbers mean as a result

The absolute milliseconds in E2 are this machine's, with an **overhead of 0.33 ms** per
query that a real network does not have. What travels is the relationship: the cost per
extra round trip rises one-for-one with the round trip, measured here at a **slope of
1.05**. A reader with a real network and a real database will get different milliseconds
and the same slope, because the slope is a statement about serialisation rather than about
sleeping.
