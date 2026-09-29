# A10 流式重组

`engineering/2026-09-24/scripts/test_sse_reassembly.py` 存在。没有对网络运行。

测试函数：

- `test_split_utf8_survives_line_buffer`
- `test_string_chunks_do_not_parse_a_partial_line`
- `test_eof_does_not_invent_done`
- `test_finish_plus_done_is_stop_even_with_a_dropped_malformed_frame`
- `test_duplicate_and_out_of_order_ids_append_in_arrival_order`
- `test_tail_stripper_drops_a_diverging_prefix`
- `test_client_reassembly_utf8_duplicate_order_and_crlf`
- `test_disconnect_closes_nested_generators`
