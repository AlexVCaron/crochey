# crochey
Crochet pattern interface for humans

## Quick start

```bash
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`.

## What is included

- Web UI to upload an input image and keep it loaded in browser memory for preview.
- Backend options for image subsampling (primary), optional oversampling, and resampling mode.
- Endpoint that returns before/after samples.
- Optional output save path (relative to backend output base directory).
- Static web server provided by Flask.

## Tests

```bash
python -m unittest discover -s tests -q
```
