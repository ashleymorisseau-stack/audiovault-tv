import json
import queue
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from pathlib import Path

class VoiceControl:
    def __init__(self, model_path="vosk-model-small-en-us-0.15"):
        """Initialize voice recognition"""
        self.model_path = Path(model_path)
        self.model = None
        self.recognizer = None
        self.is_listening = False
        self.wake_word_active = False
        self.audio_queue = queue.Queue()
        self.wake_word = "sam"
        
        # Initialize model
        if self.model_path.exists():
            self.model = Model(str(self.model_path))
            self.recognizer = KaldiRecognizer(self.model, 16000)
        else:
            raise FileNotFoundError(f"Vosk model not found at {model_path}")
    
    def audio_callback(self, indata, frames, time, status):
        """Callback for audio stream"""
        if status:
            print(f"Audio status: {status}")
        self.audio_queue.put(bytes(indata))
    
    def listen(self, duration=5):
        """Listen for speech for specified duration (seconds)"""
        if not self.model:
            return None
        
        self.is_listening = True
        self.recognizer.Reset()
        
        try:
            with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                                 channels=1, callback=self.audio_callback):
                
                import time
                start_time = time.time()
                
                while time.time() - start_time < duration and self.is_listening:
                    data = self.audio_queue.get()
                    
                    if self.recognizer.AcceptWaveform(data):
                        result = json.loads(self.recognizer.Result())
                        text = result.get('text', '').strip()
                        if text:
                            return text
                
                # Get final result
                result = json.loads(self.recognizer.FinalResult())
                text = result.get('text', '').strip()
                return text if text else None
                
        except Exception as e:
            print(f"Voice recognition error: {e}")
            return None
        finally:
            self.is_listening = False
    
    def listen_for_wake_word(self, callback):
        """Continuously listen for wake word, then command"""
        if not self.model:
            return
        
        self.wake_word_active = True
        self.recognizer.Reset()
        
        try:
            with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                                 channels=1, callback=self.audio_callback):
                
                while self.wake_word_active:
                    data = self.audio_queue.get()
                    
                    if self.recognizer.AcceptWaveform(data):
                        result = json.loads(self.recognizer.Result())
                        text = result.get('text', '').strip().lower()
                        
                        if text:
                            # Check for wake word
                            if self.wake_word in text:
                                # Wake word detected, notify callback
                                callback('wake_word_detected')
                                
                                # Listen for command (3 seconds after wake word)
                                self.recognizer.Reset()
                                import time
                                start_time = time.time()
                                command_text = ""
                                
                                while time.time() - start_time < 3 and self.wake_word_active:
                                    data = self.audio_queue.get()
                                    
                                    if self.recognizer.AcceptWaveform(data):
                                        result = json.loads(self.recognizer.Result())
                                        command_text = result.get('text', '').strip()
                                        if command_text:
                                            break
                                
                                # Get final result if nothing yet
                                if not command_text:
                                    result = json.loads(self.recognizer.FinalResult())
                                    command_text = result.get('text', '').strip()
                                
                                # Send command to callback
                                if command_text:
                                    callback('command', command_text)
                                else:
                                    callback('no_command')
                                
                                # Reset for next wake word
                                self.recognizer.Reset()
                
        except Exception as e:
            print(f"Wake word listening error: {e}")
            callback('error', str(e))
        finally:
            self.wake_word_active = False
    
    def stop_listening(self):
        """Stop listening"""
        self.is_listening = False
        self.wake_word_active = False
    
    def parse_command(self, text):
        """Parse recognized text into a command"""
        if not text:
            return None
        
        text = text.lower().strip()
        
        # Play/Pause commands
        if any(word in text for word in ['play', 'pause', 'resume', 'stop']):
            return 'play_pause'
        
        # Channel commands
        if 'next channel' in text:
            return 'next_channel'
        if 'previous channel' in text or 'last channel' in text:
            return 'prev_channel'
        
        # Navigation commands
        if 'next file' in text or 'next track' in text:
            return 'next_file'
        if 'previous file' in text or 'previous track' in text or 'last file' in text:
            return 'prev_file'
        if 'next folder' in text or 'next season' in text:
            return 'next_folder'
        if 'previous folder' in text or 'previous season' in text or 'last folder' in text:
            return 'prev_folder'
        
        # Seek commands
        if 'rewind' in text or 'go back' in text or 'back' in text:
            return 'rewind'
        if 'forward' in text or 'skip' in text or 'fast forward' in text:
            return 'fastforward'
        
        # AudioVault commands
        if 'search movie' in text or 'find movie' in text:
            # Extract query after the keyword
            for keyword in ['search movies', 'search movie', 'find movies', 'find movie']:
                if keyword in text:
                    query = text.split(keyword, 1)[1].strip()
                    return ('search_movies', query) if query else 'search_movies'
            return 'search_movies'
        if 'search show' in text or 'find show' in text or 'search tv' in text:
            for keyword in ['search tv shows', 'search tv show', 'search shows', 'search show', 'find shows', 'find show', 'search tv']:
                if keyword in text:
                    query = text.split(keyword, 1)[1].strip()
                    return ('search_shows', query) if query else 'search_shows'
            return 'search_shows'
        if 'download' in text:
            return 'download'
        
        return None
