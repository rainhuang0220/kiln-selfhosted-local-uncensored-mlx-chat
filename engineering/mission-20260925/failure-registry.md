# Failure registry, 2026-09-25 12:47 CST

## Short generation woke a large swap write

One non-streaming request to `127.0.0.1:8081/v1/chat/completions`, `max_tokens=16`, `temperature=0`, prompt "Reply with exactly kiln-ok".

| Item | Value |
| --- | --- |
| Wall time | 15.843 s |
| finish_reason | stop |
| Content | kiln-ok |
| prompt_tokens | 18 |
| completion_tokens | 4 |
| Swapouts before | 73691883 |
| Swapouts after | 74080535 |
| Delta | 388652 pages |

At the 16 KiB page size reported by `memory_pressure`, that delta is about 5.93 GiB of swap writes. The swap file then grew from 14336 MiB to 16384 MiB. Used swap after the run was 15066.69 MiB, with 1317.31 MiB free. MLX PID 1581 stayed up.

A 20k prefill is larger than this request. It was not started. The stop rule is the swapout burst, not the older idle swap stock. Before this request, a 20 second idle sample had a swapout delta of 0.

## Kiln did not observe that generation

`POST /chat` without a session returned 401. `~/Library/Application Support/kiln/api.env` contains exposure flags and no bootstrap username or password. The live watch therefore stays `UNVERIFIED`. No password was printed and no account was created.

## Not claimed

Browser Stop/Continue, public login, 20000 Chinese characters, 20000 tokens, 50 scored items, a 2x TTFT path, and a production 3 minute recovery were not measured.
