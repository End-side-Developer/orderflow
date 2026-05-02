# Multi-Language Support Guide

OrderFlow supports case files in seven languages: English, Hindi, Tamil, Telugu, Kannada, Malayalam, and Marathi. This guide explains how the system detects, translates, and preserves multi-language documents.

## Table of Contents

1. [Overview](#overview)
2. [Supported Languages](#supported-languages)
3. [Architecture](#architecture)
4. [Setup & Configuration](#setup--configuration)
5. [Usage](#usage)
6. [Troubleshooting](#troubleshooting)

## Overview

When a court judgment is uploaded to OrderFlow:

1. **Language Detection**: The system automatically detects the document's language (with user override)
2. **Translation to English**: For optimal AI extraction, case files are translated to English
3. **Extraction**: Obligations and directives are extracted using the English translation
4. **Multi-Language Export**: Users can download action plans in their preferred language

**Key Principle**: Original files are preserved for audit trail and compliance; translation is automatic but fully tracked.

## Supported Languages

| Code | Language | Native | Status |
|------|----------|--------|--------|
| en | English | English | Fully supported |
| hi | Hindi | हिन्दी | Fully supported |
| ta | Tamil | தமிழ் | Fully supported |
| te | Telugu | తెలుగు | Fully supported |
| kn | Kannada | ಕನ್ನಡ | Fully supported |
| ml | Malayalam | മലയാളം | Fully supported |
| mr | Marathi | मराठी | Fully supported |

### Language Detection Accuracy

- **English documents**: 95%+ accuracy
- **Major Indian languages (Hindi, Tamil, Telugu)**: 85–95% accuracy
- **Minority languages (Kannada, Malayalam, Marathi)**: 80–90% accuracy

*Note: Accuracy depends on text length. Minimum 50 characters recommended for reliable detection.*

### Translation Accuracy

Translations are performed using LibreTranslate (open-source, self-hosted).

- **High accuracy**: Legal structure, case IDs, dates, names (usually 95%+ fidelity)
- **Variable accuracy**: Specialized legal terminology may need manual review
- **Preserved in English**: Source citations, case numbers, and technical terms remain in English for accuracy

## Architecture

### Components

```
Upload PDF (any language)
       ↓
   [Language Detection] ← langdetect (Python library)
       ↓
  Auto-detect language code + confidence score
       ↓
   [Translation Service] ← LibreTranslate (optional if already English)
       ↓
  Translate to English (if needed)
       ↓
  [AI Extraction] ← LangGraph + LLM
       ↓
  Extract obligations + citations
       ↓
  [Multi-Language Export] ← Translate back to user's preferred language
       ↓
  Download action plan (JSON/PDF/Markdown)
```

### Database Schema

The `documents` table stores language metadata:

```sql
-- Language fields added to documents table
source_language: VARCHAR(8)           -- User-selected or detected language
auto_detected_language: VARCHAR(8)    -- Language detected by system
language_confidence: NUMERIC(5,4)     -- Confidence score (0.0-1.0)
translated_text_stored: BOOLEAN       -- Whether translation is cached
```

### Services

**Language Service** (`core/language_service.py`)
- Detects language of extracted text
- Returns language code + confidence score
- Validates language against supported list

**Translation Service** (`core/translation_service.py`)
- Calls LibreTranslate API
- Implements caching (Redis) to avoid re-translating identical text
- Includes retry logic with exponential backoff
- Async/await support for non-blocking operations

## Setup & Configuration

### 1. Docker Compose Setup

LibreTranslate is included in `docker-compose.yml`:

```yaml
libretranslate:
  image: libretranslate/libretranslate:latest
  container_name: orderflow-libretranslate
  environment:
    LIBRE_PORT: "5000"
    LIBRE_LOAD_ONLY: "hi,en,ta,te,kn,ml,mr"  # Only load needed languages
    LIBRE_THREADS: "4"
  ports:
    - "5000:5000"
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
    interval: 30s
    timeout: 10s
    retries: 5
    start_period: 60s
```

### 2. Environment Variables

Add to your `.env` or `.env.local`:

```env
# LibreTranslate service configuration
ORDERFLOW_INFRA_LIBRETRANSLATE_PORT=5000

# Backend translation settings
ORDERFLOW_TRANSLATION_SERVICE_URL=http://localhost:5000
ORDERFLOW_TRANSLATION_TIMEOUT_SECONDS=30
ORDERFLOW_TRANSLATION_CACHE_ENABLED=true
ORDERFLOW_TRANSLATION_CACHE_TTL_SECONDS=86400  # 24 hours
```

### 3. Start Services

```bash
# Start infrastructure (includes LibreTranslate)
cd app/infra
docker-compose up -d libretranslate postgres redis

# Verify LibreTranslate health
curl http://localhost:5000/health
# Response: {"status":"OK"}
```

### 4. Install Python Dependencies

```bash
cd app/backend
pip install -e .

# Or with pip-compile if using requirements.txt
pip install langdetect aiohttp tenacity
```

### 5. Run Database Migration

```bash
cd app/backend
alembic upgrade head
# This adds language columns to the documents table
```

## Usage

### 1. Upload with Language Detection

**User Flow:**

1. User uploads a PDF (e.g., a Hindi court judgment)
2. System displays detected language: "हिन्दी (Hindi) — Confidence: 92%"
3. User can override if detection was incorrect
4. System translates to English for extraction

**API:**

```python
# POST /documents
{
  "source_file_name": "case_2024_001.pdf",
  "source_file_type": "application/pdf",
  "source_file_size": 245000,
  "metadata": {
    "user_language_preference": "hi"  # Optional user preference
  }
}

# Response
{
  "ok": true,
  "data": {
    "id": "uuid-here",
    "source_language": "hi",  # Detected/set language
    "auto_detected_language": "hi",
    "language_confidence": 0.92,
    "translated_text_stored": false,
    "status": "processing",
    ...
  }
}
```

### 2. Language Auto-Detection

**Backend Process:**

```python
from orderflow_api.core.language_service import detect_language

# Extract PDF text
pdf_text = extract_pdf_text(pdf_bytes)

# Detect language
result = detect_language(pdf_text)

# result.detected_language → "hi"
# result.confidence → 0.92
# result.is_supported → True
```

### 3. Translation (Internal)

When a non-English document is detected, the intake pipeline translates it:

```python
from orderflow_api.core.translation_service import TranslationService, TranslationServiceConfig

config = TranslationServiceConfig(
    service_url="http://localhost:5000",
    timeout_seconds=30,
)
service = TranslationService(config, cache_backend=redis_client)

# Translate Hindi text to English
hindi_text = "यह एक न्यायालय का निर्णय है।"
english_text = await service.translate(hindi_text, "hi", "en")
# → "This is a court judgment."
```

### 4. Export to User's Language

**API:**

```python
# POST /obligations/{obligation_id}/export
{
  "export_language": "hi",  # User's preferred language
  "format": "pdf"  # or "json", "markdown"
}

# Response
{
  "ok": true,
  "data": {
    "export_id": "exp-uuid",
    "obligation_id": "obl-uuid",
    "export_language": "hi",
    "format": "pdf",
    "download_url": "/api/exports/exp-uuid/download",
    "file_name": "action_plan_case_2024_001_hi_20260424.pdf",
    "generated_at": "2026-04-24T10:30:00Z"
  }
}
```

**Download:**

```bash
GET /api/exports/exp-uuid/download

# Returns PDF with obligations in Hindi
# Original citations remain in English for accuracy
```

## Troubleshooting

### Issue: Language Detection Fails (Defaults to English)

**Symptoms:**
- Upload a Hindi document, system detects "English"
- Confidence score is 0.0

**Causes:**
- PDF text is very short (< 50 characters)
- Text is mostly numbers or special characters
- Mixed-language content with English-heavy bias

**Solutions:**

1. **Ensure sufficient text**: PDFs with < 50 words will not detect reliably
2. **Check PDF extraction**: Verify PDF text extraction isn't failing (OCR issue)
3. **Manual override**: User can manually select language on upload form
4. **Check logs**:
   ```bash
   docker-compose logs orderflow-backend | grep "Language detected"
   ```

### Issue: Translation Fails / Timeout

**Symptoms:**
- "Translation request timed out" error
- Extraction stuck at "Translating..."
- 503 Service Unavailable from LibreTranslate

**Causes:**
- LibreTranslate service not running
- Network connectivity issue
- LibreTranslate overloaded (especially first request with new language pair)
- Timeout set too low

**Solutions:**

1. **Check LibreTranslate health**:
   ```bash
   curl http://localhost:5000/health
   # Should return {"status":"OK"}
   ```

2. **Check service logs**:
   ```bash
   docker-compose logs libretranslate
   ```

3. **Increase timeout**: Update `.env`:
   ```env
   ORDERFLOW_TRANSLATION_TIMEOUT_SECONDS=60  # Increased from 30
   ```

4. **Restart service**:
   ```bash
   docker-compose restart libretranslate
   # Allow 60s for startup before first use
   ```

5. **Scale LibreTranslate** (for production):
   ```yaml
   libretranslate:
     deploy:
       resources:
         limits:
           memory: 4G
       replicas: 2  # Run multiple instances behind load balancer
   ```

### Issue: Translation Cache Not Working

**Symptoms:**
- Same obligation translated multiple times (slow, repeated API calls)
- Redis shows no cache entries

**Causes:**
- Redis connection failed
- Cache TTL too short
- Cache disabled in config

**Solutions:**

1. **Check Redis connection**:
   ```bash
   redis-cli ping
   # Should return PONG
   ```

2. **Verify cache is enabled**:
   ```env
   ORDERFLOW_TRANSLATION_CACHE_ENABLED=true
   ```

3. **Check cache keys**:
   ```bash
   redis-cli keys "translation:*"
   # Should show cache keys like: translation:hi:en:abc123def456
   ```

4. **Clear cache if needed**:
   ```bash
   redis-cli FLUSHDB  # Clear all keys
   ```

### Issue: Translation Quality Poor / Incorrect Legal Terms

**Symptoms:**
- Technical legal terms are mistranslated
- Proper names are corrupted
- Obligation meaning is changed

**Causes:**
- Legal terminology not in LibreTranslate's training data
- Regional legal variations not recognized
- Short phrases without context

**Solutions:**

1. **Add manual review step** for low-confidence translations:
   - Flag translations with confidence < 0.7 for manual review
   - Reviewer can edit translated text before finalization

2. **Preserve source citations**: Ensure original case citations remain in English for accuracy

3. **Use context in prompts**: LLM extraction prompts include source language info:
   ```
   "This document was originally in [Hindi]. 
    Translation performed with [confidence]. 
    Preserve original meaning and legal citations."
   ```

4. **Fallback to original**: If translation confidence is very low, extraction can attempt the original language text

### Issue: Database Migration Failed

**Symptoms:**
- `alembic upgrade head` fails
- Error: "column source_language already exists"

**Solutions:**

```bash
# Check current migration status
alembic current

# If stuck, see migration history
alembic history

# Downgrade if needed (careful!)
alembic downgrade -1

# Re-run upgrade
alembic upgrade head
```

## Performance Tuning

### Translation Caching

For documents with repeated obligations:

```python
# Cache is automatically managed, but can be tuned:
ORDERFLOW_TRANSLATION_CACHE_TTL_SECONDS=86400  # 24 hours
ORDERFLOW_TRANSLATION_CACHE_MAX_SIZE=10000      # Max cache keys
```

### LibreTranslate Optimization

```yaml
# docker-compose.yml
libretranslate:
  environment:
    LIBRE_THREADS: "8"              # Increase for parallel requests
    LIBRE_LOAD_ONLY: "hi,en,ta,te,kn,ml,mr"  # Only load needed languages
  deploy:
    resources:
      limits:
        memory: 2G                  # Allocate sufficient memory
```

### Batch Translation

For bulk obligation exports:

```python
# Translate multiple obligations efficiently
obligations = [...10 obligations...]
await translation_service.translate_batch(
    [obl.description for obl in obligations],
    source_lang="en",
    target_lang="hi",
    use_cache=True  # Reuse cached translations
)
```

## Monitoring & Logging

### Enable Debug Logging

```python
import logging
logging.getLogger("orderflow_api.core.language_service").setLevel(logging.DEBUG)
logging.getLogger("orderflow_api.core.translation_service").setLevel(logging.DEBUG)
```

### OpenTelemetry Tracing

Language detection and translation are instrumented with OTel spans:

```
orderflow.language.detect (span)
  ├── duration_ms
  ├── detected_language
  └── confidence

orderflow.translation.translate (span)
  ├── source_language
  ├── target_language
  ├── duration_ms
  └── cache_hit (true/false)
```

Access traces via Jaeger UI: http://localhost:16686

## References

- **Language Detection**: [langdetect](https://github.com/Mimino666/langdetect) — Fast language identification
- **Translation**: [LibreTranslate](https://github.com/LibreTranslate/LibreTranslate) — Self-hosted open-source machine translation
- **Supported Languages**: [ISO 639-1 Codes](https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes)
