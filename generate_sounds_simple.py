#!/usr/bin/env python3
"""
Simple Sound Effect Generator
Create basic sound effects using scipy (no AI needed)
"""

import numpy as np
from scipy.io import wavfile
import os

def generate_tone(frequency, duration, sample_rate=44100):
    """Generate a pure tone"""
    t = np.linspace(0, duration, int(sample_rate * duration))
    return np.sin(2 * np.pi * frequency * t)

def apply_envelope(audio, attack=0.01, release=0.01, sample_rate=44100):
    """Apply fade in/out to avoid clicks"""
    attack_samples = int(sample_rate * attack)
    release_samples = int(sample_rate * release)
    
    # Fade in
    audio[:attack_samples] *= np.linspace(0, 1, attack_samples)
    # Fade out
    audio[-release_samples:] *= np.linspace(1, 0, release_samples)
    
    return audio

def generate_startup_chime(filename="startup.wav"):
    """Generate a pleasant startup chime (ascending notes)"""
    sample_rate = 44100
    
    # Three ascending notes: C, E, G (major chord)
    note1 = generate_tone(523, 0.15, sample_rate)  # C5
    note2 = generate_tone(659, 0.15, sample_rate)  # E5
    note3 = generate_tone(784, 0.3, sample_rate)   # G5
    
    # Add small gaps
    gap = np.zeros(int(sample_rate * 0.05))
    
    # Combine
    audio = np.concatenate([note1, gap, note2, gap, note3])
    audio = apply_envelope(audio, attack=0.01, release=0.1)
    
    # Normalize and convert to 16-bit
    audio = audio / np.max(np.abs(audio)) * 0.8
    audio = (audio * 32767).astype(np.int16)
    
    wavfile.write(filename, sample_rate, audio)
    print(f"✓ Generated: {filename}")

def generate_notification_beep(filename="notification.wav"):
    """Generate a short notification beep"""
    sample_rate = 44100
    
    # High pitched beep
    audio = generate_tone(800, 0.15, sample_rate)
    audio = apply_envelope(audio, attack=0.005, release=0.05)
    
    # Normalize
    audio = audio / np.max(np.abs(audio)) * 0.7
    audio = (audio * 32767).astype(np.int16)
    
    wavfile.write(filename, sample_rate, audio)
    print(f"✓ Generated: {filename}")

def generate_error_sound(filename="error.wav"):
    """Generate an error buzz"""
    sample_rate = 44100
    
    # Low buzz
    audio = generate_tone(200, 0.4, sample_rate)
    audio = apply_envelope(audio, attack=0.01, release=0.1)
    
    # Normalize
    audio = audio / np.max(np.abs(audio)) * 0.7
    audio = (audio * 32767).astype(np.int16)
    
    wavfile.write(filename, sample_rate, audio)
    print(f"✓ Generated: {filename}")

def generate_success_sound(filename="success.wav"):
    """Generate a success chime (two ascending notes)"""
    sample_rate = 44100
    
    # Two notes: G, C (perfect fifth)
    note1 = generate_tone(392, 0.15, sample_rate)  # G4
    note2 = generate_tone(523, 0.25, sample_rate)  # C5
    
    gap = np.zeros(int(sample_rate * 0.05))
    audio = np.concatenate([note1, gap, note2])
    audio = apply_envelope(audio, attack=0.01, release=0.1)
    
    # Normalize
    audio = audio / np.max(np.abs(audio)) * 0.8
    audio = (audio * 32767).astype(np.int16)
    
    wavfile.write(filename, sample_rate, audio)
    print(f"✓ Generated: {filename}")

def main():
    print("=" * 50)
    print("Simple Sound Effect Generator")
    print("=" * 50)
    print("\nOptions:")
    print("1. Startup chime (pleasant ascending notes)")
    print("2. Notification beep (short high beep)")
    print("3. Error sound (low buzz)")
    print("4. Success sound (two ascending notes)")
    print("5. Generate all")
    
    choice = input("\nSelect (1-5): ").strip()
    
    if choice == "1":
        generate_startup_chime()
    elif choice == "2":
        generate_notification_beep()
    elif choice == "3":
        generate_error_sound()
    elif choice == "4":
        generate_success_sound()
    elif choice == "5":
        print("\nGenerating all sounds...")
        generate_startup_chime()
        generate_notification_beep()
        generate_error_sound()
        generate_success_sound()
        print("\n✓ All sounds generated!")
    else:
        print("Invalid choice")
        return
    
    print("\nConvert to MP3 if needed:")
    print("  ffmpeg -i filename.wav filename.mp3")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled")
    except Exception as e:
        print(f"\nError: {e}")
