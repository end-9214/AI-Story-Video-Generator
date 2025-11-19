import edge_tts
import asyncio

async def generate_audio(text, voice="bn-IN-BashkarNeural", output_file="output.mp3"):
    communicator = edge_tts.Communicate(text=text, voice=voice, rate="+10%")
    await communicator.save(output_file)

def main():
    prompt_text = "His selfless acts inspired his classmates to also start helping others, creating a ripple effect of kindness in the community."
    selected_voice = "en-IN-PrabhatNeural"
    asyncio.run(generate_audio(text=prompt_text, voice=selected_voice, output_file="generated_speech.mp3"))


if __name__ == "__main__":
    main()