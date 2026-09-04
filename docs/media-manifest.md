# Generation weight layout

Weights live next to the Kiln checkout, not inside git.

| Role | Directory name (sibling of `kiln/`) |
| --- | --- |
| Chat | `qwen3.5-9b-hauhau-aggressive-mxfp4` |
| Image default | `image-z-image-turbo-mflux-4bit` |
| Image optional | `image-flux2-klein-4b-mflux-4bit` |
| Video DiT | `video-nsfw-wan-1.3b` |
| Video MLX | `video-nsfw-wan-1.3b-mlx` |
| Video aux T5/VAE | `video-wan21-t2v-1.3b-aux` |

Override paths with settings / environment variables (`IMAGE_ZIMAGE_DIR`, `VIDEO_WAN_MLX_DIR`, …). Do not commit weight files.
