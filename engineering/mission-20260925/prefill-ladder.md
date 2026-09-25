# Prefill ladder, 2026-09-25

MLX PID stayed 1581. These calls went to `127.0.0.1:8081` directly. They do not update Kiln's readiness watch. Kiln READY came from the server-side probe, recorded separately.

Temperature 0. `max_tokens` 8 or 16. `cached_tokens` was 0 on every long call. Swapout deltas are pages from `memory_pressure`.

| Step | Chars | Server prompt tokens | Seconds | finish | Swapout delta | Notes |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| Warm 16-token repeat | short | 18 | 0.519 | stop | 0 | Content `kiln-ok`. Model already resident. |
| About 1k | 1320 | 1336 | 6.196 | stop | 0 | Completion 2. |
| About 4k | 4800 | 4416 | 19.651 | stop | 0 | Footprint 5665 MB. |
| 20000 repeated 窑 | 20000 | 20014 | 96.421 | stop | 0 | Reply `MARK8841`. This is one 20k-token-scale prefill, not the older 13476-token character baseline. Footprint 7323 MB. |
| 20000 varied sentences | 20000 | 16169 | 77.644 | stop | 0 | Reply `MARK8841`. Not the 65.1 s / 13476-token baseline. Footprint 7945 MB. |

The server token counts are far above 4096 and 8192, and both 20000-character prompts ended with a marker the model repeated. That is evidence against silent truncation for these two prompts. It is not the 50-item scored set, not a Kiln BFF measurement, and not a 2x TTFT improvement. The historical 65.1 s and 100.8 s numbers stay the baselines for different texts.

No MLX restart. After the ladder, swapouts were still the same counter as before the 1k step.
