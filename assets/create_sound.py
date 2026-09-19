import pyttsx3
from pathlib import Path

# Save inside the same assets folder
assets = Path(__file__).resolve().parent

# First create a WAV file
output = assets / "success_sound.wav"

engine = pyttsx3.init()

engine.setProperty("rate", 175)
engine.setProperty("volume", 0.9)

message = "This post has been successfully uploaded on Instagram."

engine.save_to_file(message, str(output))
engine.runAndWait()

print("====================================")
print("SUCCESS!")
print("Sound file created:")
print(output.resolve())
print("====================================")
