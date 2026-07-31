import boto3
import os
from pathlib import Path

# Configuration
BUCKET_NAME = "mp3-player-updates"  # Change this to your S3 bucket name
S3_PREFIX = "mp3-player/"  # Folder in S3 bucket
LOCAL_DIR = Path(__file__).parent

# Files to upload (exclude the channels JSON file and vosk model)
FILES_TO_UPLOAD = [
    "main.py",
    "audio_player.py",
    "playlist_manager.py",
    "channel_manager.py",
    "voice_control.py",
    "player_logger.py",
    "audiovault_client.py",
    "youtube_client.py",
    "auto_updater.py",
    "sounds/startup.mp3",
    "sounds/outro.mp3",
    "sounds/start_of_request.wav",
    "sounds/end_of_request.wav",
    "sounds/remote.mp3",
    "tools/ffmpeg.exe",
    "tools/ffprobe.exe",
    "tools/ffplay.exe",
    "requirements.txt",
    "README.md",
    "SETUP.md",
    "IMPLEMENTATION_PLAN.md",
    "VOICE_COMMANDS.md"
]

def upload_to_s3():
    """Upload program files to S3"""
    try:
        s3 = boto3.client('s3')
        print("Connecting to S3...")
        
        uploaded_files = []
        
        for filename in FILES_TO_UPLOAD:
            local_path = LOCAL_DIR / filename
            
            if not local_path.exists():
                print(f"Warning: {filename} not found locally, skipping")
                continue
            
            s3_key = f"{S3_PREFIX}{filename}"
            
            try:
                print(f"Uploading: {filename}")
                s3.upload_file(str(local_path), BUCKET_NAME, s3_key)
                uploaded_files.append(filename)
            except Exception as e:
                print(f"Error uploading {filename}: {e}")
        
        # Summary
        print("\n=== Upload Complete ===")
        print(f"Uploaded {len(uploaded_files)} files:")
        for f in uploaded_files:
            print(f"  - {f}")
        
        print(f"\nFiles are now available at: s3://{BUCKET_NAME}/{S3_PREFIX}")
        print("Users can run update.py to download the latest version")
            
    except Exception as e:
        print(f"Error connecting to S3: {e}")
        print("\nMake sure you have:")
        print("1. AWS credentials configured (run 'aws configure')")
        print("2. Updated BUCKET_NAME in this script")
        print("3. S3 bucket created")
        print("4. Proper S3 permissions")

if __name__ == "__main__":
    print("AudioVault TV Upload Script")
    print("=" * 40)
    
    response = input("Upload all files to S3? (yes/no): ")
    if response.lower() in ['yes', 'y']:
        upload_to_s3()
    else:
        print("Upload cancelled")
    
    input("\nPress Enter to exit...")
