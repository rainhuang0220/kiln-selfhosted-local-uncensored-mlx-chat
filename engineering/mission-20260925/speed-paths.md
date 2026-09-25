# Three speeds, not one number

Date: 2026-09-25. MLX PID 1581 was not restarted. Calls went to `127.0.0.1:8081`. Temperature 0. Swapout delta was 0 on every call below.

The source is `eval/semantic-20k.txt`, 20000 characters. The question was the unpaid id, whose answer is 44091.

| Path | Prompt tokens | Cached tokens | Seconds | Answer |
| --- | ---: | ---: | ---: | --- |
| Cold full text | 13240 | 0 | 62.754 | 44091 |
| Same prompt again | 13240 | 13236 | 0.588 | 44091 |
| Retrieval, 500 characters served | 335 | 0 | 2.477 | 44091 |
| Extractive compression, 2426 characters | 1890 | 0 | 8.856 | 44091 |

Compression CPU time was under 0.001 second. The compressor kept the sentences that contain 44091, 128400, 没有批准, InvoiceBatch.close, and 187. It is not LLMLingua. A second model was not loaded beside the resident 9B.

The old cold baselines remain 65.1 seconds for a different 20000-character text (13476 tokens) and 100.8 seconds for a 20000-token text. This cold run is 62.754 seconds at 13240 tokens. That is not a 2x improvement of full-text prefill.

Retrieval on this one question is 62.754 / 2.477, about 25 times the cold full-text time, with the same answer. Compression is 62.754 / 8.856, about 7 times, also with the same answer. Those ratios belong to the retrieval path and the compression path. They are not the full-text number and they are not the cache-reuse number.

Four more retrieval questions on the same document, 预算, 外包, 缺页, and 函数, all returned the expected value. Each took about 2 seconds and 330 prompt tokens.

Decode on a short stream, three runs, 59 content events: about 21.6 events per second after the first event. A non-streaming twin produced 60 completion tokens. That is in line with the 21.4 tok/s median baseline, not a new 20k decode measurement.

The 50 shorter documents are a different set. Verbatim median was 4.253 seconds. Retrieval median was 2.328 seconds. Normalized hit rate 49/50. See `eval/README.md`.
