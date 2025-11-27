import os
import json
import uuid
import base64
import docker
import requests
from flask import Flask, request, jsonify, send_file
from moviepy import VideoFileClip, concatenate_videoclips
from pydub import AudioSegment
from faster_whisper import WhisperModel

app = Flask(__name__)

print("Loading Whisper model...")
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

def transcribe_video(video_path, language='ru'):
    segments, _ = whisper_model.transcribe(video_path, beam_size=5, language=language)
    return [segment.text for segment in segments]

def group_sentences(segments, min_chars=200, max_chars=310):
    import re
    
    full_text = " ".join(segments)
    sentences = re.split(r'(?<=[.!?])\s+', full_text.strip())
    
    groups = []
    current = []
    
    for sentence in sentences:
        test = " ".join(current + [sentence])
        
        if len(test) > max_chars and len(current) >= 2:
            groups.append(" ".join(current))
            current = [sentence]
        else:
            current.append(sentence)
    
    if current:
        combined = " ".join(current)
        if groups and len(combined) < min_chars:
            groups[-1] = groups[-1] + " " + combined
        else:
            groups.append(combined)
    
    return groups

def generate_tts_segment(text, voice_sample_path, output_path):
    with open(voice_sample_path, 'rb') as f:
        audio_data = f.read()
    audio_b64 = base64.b64encode(audio_data).decode('utf-8')
    
    response = requests.post(
        "http://tts:8000/speech",
        json={
            "text": text,
            "audio_prompt": audio_b64,
            "exaggeration": 0.8,
            "cfg": 0.25,
            "temperature": 0.35
        },
        timeout=120
    )
    
    if response.status_code != 200:
        raise Exception(f"TTS failed: {response.text}")
    
    with open(output_path, 'wb') as f:
        f.write(response.content)
    
    return output_path

def split_video_by_audio(video_path, audio_files, work_dir):
    os.makedirs(work_dir, exist_ok=True)
    video = VideoFileClip(video_path)
    
    current_time = 0
    video_parts = []
    
    for i, audio_file in enumerate(audio_files):
        audio_seg = AudioSegment.from_wav(audio_file)
        duration = audio_seg.duration_seconds
        
        video_part_path = os.path.join(work_dir, f"video_{i}.mp4")
        
        video_part = video.subclipped(current_time, current_time + duration)
        video_part.write_videofile(video_part_path, codec="libx264", audio=False)
        video_part.close()
        
        video_parts.append(video_part_path)
        current_time += duration
    
    video.close()
    return video_parts

def run_lipsync_in_container(video_path, audio_path, output_path):
    client = docker.from_env()
    container = client.containers.get('lipsync_service')
    
    video_container_path = video_path.replace('/app/temp', '/home/temp')
    audio_container_path = audio_path.replace('/app/temp', '/home/temp')
    output_container_path = output_path.replace('/app/temp', '/home/temp').replace('/app/output', '/home/output')
    
    cmd = [
        "python", "-m", "scripts.inference",
        "--unet_config_path", "configs/unet/stage2.yaml",
        "--inference_ckpt_path", "checkpoints/latentsync_unet.pt",
        "--inference_steps", "20",
        "--guidance_scale", "1.5",
        "--enable_deepcache",
        "--video_path", video_container_path,
        "--audio_path", audio_container_path,
        "--video_out_path", output_container_path
    ]
    
    result = container.exec_run(
    cmd,
    workdir="/app",   
    environment={"CUDA_VISIBLE_DEVICES": "0"}
    )
    
    if result.exit_code != 0:
        raise Exception(f"Lipsync failed: {result.output.decode()}")
    
    return output_path

def concatenate_videos(video_parts, output_path):
    clips = [VideoFileClip(part) for part in video_parts]
    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")
    
    final.close()
    for clip in clips:
        clip.close()

@app.route('/process', methods=['POST'])
def process_video():
    """
    Main API endpoint. Send it:
    - video: source video file
    - voice_sample: audio sample for TTS cloning
    
    Returns: Job ID to check status later
    """
    if 'video' not in request.files or 'voice_sample' not in request.files:
        return jsonify({"error": "Missing video or voice_sample"}), 400
    
    video_file = request.files['video']
    voice_file = request.files['voice_sample']
    
    job_id = str(uuid.uuid4())
    job_dir = f"/app/temp/jobs/{job_id}"
    os.makedirs(job_dir, exist_ok=True)
    
    video_path = f"{job_dir}/source_video.mp4"
    voice_path = f"{job_dir}/voice_sample.wav"
    video_file.save(video_path)
    voice_file.save(voice_path)
    
    try:
        # Step 1: Transcribe
        print(f"[{job_id}] Transcribing video...")
        segments = transcribe_video(video_path, language='ru')
        grouped_texts = group_sentences(segments)
        
        # Step 2: Generate TTS for each segment
        print(f"[{job_id}] Generating {len(grouped_texts)} TTS segments...")
        audio_dir = f"{job_dir}/audio_segments"
        os.makedirs(audio_dir, exist_ok=True)
        
        audio_files = []
        for i, text in enumerate(grouped_texts):
            output_path = f"{audio_dir}/segment_{i}.wav"
            generate_tts_segment(text, voice_path, output_path)
            audio_files.append(output_path)
        
        # Step 3: Split video by audio segments
        print(f"[{job_id}] Splitting video...")
        video_parts = split_video_by_audio(
            video_path,
            audio_files,
            f"{job_dir}/video_parts"
        )
        
        # Step 4: Lipsync each segment
        print(f"[{job_id}] Processing lipsync...")
        processed_parts = []
        
        for i, (video, audio) in enumerate(zip(video_parts, audio_files)):
            output_path = f"{job_dir}/processed_parts/processed_part{i}.mp4"
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            print(f"[{job_id}] Segment {i+1}/{len(video_parts)}...")
            run_lipsync_in_container(video, audio, output_path)
            processed_parts.append(output_path)
        
        # Step 5: Concatenate final video
        print(f"[{job_id}] Concatenating...")
        final_output = f"/app/output/{job_id}_final.mp4"
        concatenate_videos(processed_parts, final_output)
        
        return jsonify({
            "job_id": job_id,
            "status": "completed",
            "output_file": f"{job_id}_final.mp4",
            "download_url": f"/download/{job_id}"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download/<job_id>', methods=['GET'])
def download_result(job_id):
    file_path = f"/app/output/{job_id}_final.mp4"
    
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    
    return send_file(file_path, as_attachment=True)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, debug=True)