# crochey
Crochet pattern interface for humans

Convert any image into a readable crochet stitch pattern through an in-browser
UI backed by a small Python server.

## Quick start

```bash
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`.

## How it works

### Crochet space

A photograph lives in pixel space.  A crochet project lives in *crochet space*,
where every unit is one stitch and stitches have a physical aspect ratio
(typically ≈ 1.5:1 width/height for worsted weight).  The backend converts the
image by:

1. **Subsampling** (the dominant operation) – resizing the image down to the
   exact stitch × row count of the target piece.  Oversampling is accepted but
   uncommon.
2. **Colour quantization** – reducing the colour palette to N yarn colours using
   median-cut.
3. **Pattern grid rendering** – every pixel becomes a stitch-shaped coloured
   cell; guide lines mark every 5th stitch and row; column/row numbers are
   printed at guide positions.

### UI

- **Instant local preview** of the uploaded image before any server round-trip.
- **Two sizing modes**
  - *Direct*: enter stitch count and row count directly.
  - *Gauge-based*: enter your gauge (stitches/unit, rows/unit) and finished
    dimensions; the backend calculates the grid automatically.
- **Resample method** (Lanczos recommended for downscaling).
- **Yarn colours** – number of palette colours (0 = skip quantization).
- **Pattern grid cell dimensions** – default 24 × 16 px (1.5:1 aspect ratio).
- **Guide every N stitches** – major grid lines + number labels.
- **Save pattern** – saves the rendered grid PNG on the server and provides a
  download link.

### Backend modules

| File | Responsibility |
|------|----------------|
| `processor.py` | Image loading, crochet-space resampling, colour quantization, pattern grid rendering |
| `app.py` | Thin Flask routes; delegates all processing to `processor.py` |
| `templates/index.html` | Single-page UI |

## API

### `POST /api/process`

Multipart form fields:

| Field | Default | Description |
|-------|---------|-------------|
| `image` | — | Image file (any Pillow-supported format) |
| `mode` | `direct` | `"direct"` or `"gauge"` |
| `stitch_count` | orig_w / 4 | *(direct mode)* stitch count |
| `row_count` | orig_h / 4 | *(direct mode)* row count |
| `stitches_per_unit` | `14` | *(gauge mode)* stitches per unit |
| `rows_per_unit` | `12` | *(gauge mode)* rows per unit |
| `finished_width` | `20` | *(gauge mode)* finished width |
| `finished_height` | `15` | *(gauge mode)* finished height |
| `resample` | `lanczos` | `nearest` / `bilinear` / `bicubic` / `lanczos` |
| `n_colors` | `8` | Palette size (0 = skip) |
| `cell_w` | `24` | Pattern cell width in px |
| `cell_h` | `16` | Pattern cell height in px |
| `guide_every` | `5` | Major guide line interval |
| `save_output` | `false` | `"true"` to save the pattern on the server |
| `output_name` | `pattern.png` | File name for saved output |

### `GET /api/download/<name>`

Download a previously saved output file.

## Tests

```bash
python -m unittest discover -s tests -q
```
