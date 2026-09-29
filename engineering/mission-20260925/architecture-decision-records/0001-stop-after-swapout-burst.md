# Stop long-context runs after the 16-token swapout burst

Date: 2026-09-25

A direct 16-token completion on PID 1581 was enough to prove the generator can stop cleanly. It also wrote 388652 swapout pages. The mission's own stop rule is continuous swap writing during an experiment, not the mere existence of an old swap file.

The 20k character and 20k token prefill are larger than that request. They stay unrun until a later 16-token call shows the model is resident and swapouts stay nearly flat.

No MLX restart was used to hide the pressure.
