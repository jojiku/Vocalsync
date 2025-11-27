# 🎤 Vocalsync

<div align="center">

**Clone any voice from seconds of audio and transplant it onto any video**

</div>

---

## 📹 Demo

| Input | Output |
|:---:|:---:|
| **[Watch Original Video](https://github.com/user-attachments/assets/70e16d68-93c8-4b96-80cd-0673d36cef3d)** | **[Watch Result](https://github.com/user-attachments/assets/03031de1-b941-49db-8262-fc96ac9abc4c)** |
| *Original audio source* | *Cloned voice output* |

## 🎯 Overview

Automated pipeline for video dubbing with TTS voice cloning and lipsync. Provide a source video and a voice sample—the system transcribes the video, generates new audio with the cloned voice, and syncs the lips to match.

### Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│     TTS     │────▶│ Orchestrator │◀────│  Lipsync    │
│  (Whisper + │     │  (REST API)  │     │ (LatentSync)│
│ Chatterbox) │     └──────────────┘     └─────────────┘
└─────────────┘                                          
```

**TTS Component**
- Transcribes video using [Whisper](https://github.com/openai/whisper)
- Generates speech with [Chatterbox](https://github.com/resemble-ai/chatterbox) (current SOTA as of Nov 2025)

**Lipsync Component**
- Syncs lips to generated audio using [LatentSync](https://github.com/bytedance/LatentSync) (current SOTA as of Nov 2025)

**Orchestrator**
- Coordinates the pipeline and exposes REST API

---

## 🔧 Prerequisites

- Docker & Docker Compose
- NVIDIA GPU with CUDA support
- `nvidia-docker` runtime installed
- **At least 12GB VRAM** (recommended)

---

## 🚀 Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/jojiku/Vocalsync.git
   cd Vocalsync
   ```

2. **Build and start all services**
   ```bash
   sudo docker compose up --build
   ```

   > ⏱️ **First startup takes 5-10 minutes** as models download:
   > - Whisper medium (~1.5GB)
   > - ChatterboxMultilingualTTS (~2GB)

---

## 💻 Usage

Send a POST request with your video and voice sample:

```bash
curl -X POST http://localhost:8000/process \
  -F "video=@/path/to/your/video.mp4" \
  -F "voice_sample=@/path/to/voice_sample.wav"
```

### Parameters

| Parameter | Description | Format |
|-----------|-------------|--------|
| `video` | Source video file | MP4 |
| `voice_sample` | Clean audio sample for voice cloning | WAV (5-15 seconds recommended) |

---

## 🔄 Processing Pipeline

```mermaid
graph LR
    A[Upload] --> B[Transcription]
    B --> C[Text Grouping]
    C --> D[TTS Generation]
    D --> E[Video Splitting]
    E --> F[Lipsync]
    F --> G[Concatenation]
    G --> H[Download]
```

1. **Upload** - Client sends video + voice sample
2. **Transcription** - Whisper transcribes original audio
3. **Text Grouping** - Segments grouped into optimal TTS chunks (200-310 chars)
4. **TTS Generation** - ChatterboxMultilingualTTS generates audio with cloned voice
5. **Video Splitting** - Source video split into segments matching audio duration
6. **Lipsync** - LatentSync processes each segment
7. **Concatenation** - Final video assembled from processed segments
8. **Download** - Client retrieves result

---

## ⚡ Performance

**T4 GPU Benchmarks:**

| Video Length | Processing Time |
|-------------|----------------|
| Small (1-2 min) | ~15 minutes |
| Medium (5-10 min) | ~30-70 minutes |
| Large (30+ min) | ~7 hours |

> ⚠️ Processing time varies based on video length, GPU performance, and TTS chunk count.

---

## 🙏 Credits

- [**Whisper**](https://github.com/openai/whisper) by OpenAI
- [**ChatterboxMultilingualTTS**](https://github.com/resemble-ai/chatterbox)
- [**LatentSync**](https://github.com/bytedance/LatentSync) by ByteDance

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---
