from dotenv import load_dotenv
from pathlib import Path
import os
import tempfile
from typing import List, Tuple, Optional, Sequence, Dict, Any

import gradio as gr
import openai
from pydub import AudioSegment


#auth
load_dotenv()
openai_token = os.getenv("OPENAI_TOKEN")
client = openai.OpenAI(api_key=openai_token)
# tmp
SYSTEM_PROMPT = (
    "You are a helpful, concise voice assistant. "
    "Answer clearly and keep replies short unless further detail is requested."
)


def _ensure_wav(audio_path: str) -> str:
    """Convert arbitrary audio → 16‑kHz mono WAV (OpenAI Whisper’s preferred format).

    Whisper can ingest many formats, but providing a consistent WAV
    eliminates edge cases.  Returns a path to the converted file (which may
    equal the input if conversion was unnecessary)."""
    sound = AudioSegment.from_file(audio_path)
    if sound.frame_rate == 16000 and sound.channels == 1 and audio_path.lower().endswith(".wav"):
        return audio_path  # already perfect

    converted = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sound.set_frame_rate(16000).set_channels(1).export(converted.name, format="wav")
    return converted.name

# stt
def transcribe(audio_filepath: str) -> str:
    """🔉 → 📝  Whisper‑1 transcription."""
    wav_path = _ensure_wav(audio_filepath)

    with open(wav_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",
        )

    return response.strip()

def _history_to_messages(history: Sequence[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """Convert gr.Chatbot format → OpenAI chat messages."""
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    for user_msg, assistant_msg in history:
        messages.append({"role": "user", "content": user_msg})
        if assistant_msg:
            messages.append({"role": "assistant", "content": assistant_msg})
    return messages

# llm
def generate_llm_reply(conversation: List[Tuple[str, str]]) -> str:
    """🗨️  → 🤖  GPT‑4o‑mini completion."""
    messages = _history_to_messages(conversation)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=512,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()

# tts
def synthesize_speech(text: str) -> str:
    """📝 → 🔉  GPT‑4o‑mini‑TTS synthesis.

    # Returns the path to a WAV file ready for Gradio playback."""
    # response = client.audio.speech.create(
    #     model="gpt-4o-mini-tts",
    #     voice="alloy",  # change if you have additional voices
    #     input=text,
    #     response_format="wav",
    # )

    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="onyx",  # change if you have additional voices
        input=text,
        response_format="wav",
    ) as response:
        out_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        response.stream_to_file(out_path)  # 👈 built-in helper
        return out_path

# gradio glue
def process_voice_message(
    audio: Optional[str],
    chat_history: List[Tuple[str, str]],
) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    if audio is None:
        return None, chat_history

    try:
        user_text = transcribe(audio)
    except Exception as e:
        chat_history.append(("<STT error>", "Sorry, I couldn’t understand the audio."))
        return None, chat_history

    chat_history.append((user_text, ""))

    try:
        assistant_text = generate_llm_reply(chat_history)
    except Exception as e:
        chat_history[-1] = (user_text, "Sorry, something went wrong generating a reply.")
        return None, chat_history

    chat_history[-1] = (user_text, assistant_text)

    try:
        audio_reply = synthesize_speech(assistant_text)
    except Exception as e:
        audio_reply = None  # text will still display

    return audio_reply, chat_history


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Voice Chatbot") as demo:
        gr.Markdown("## 🎙️ Voice Chatbot with STT → LLM → TTS")

        chatbot = gr.Chatbot(label="Conversation", height=400)

        with gr.Row():
            audio_in = gr.Audio(
                sources=["microphone"],
                type="filepath",
                label="🎤 Record / Play",
                format="wav",
            )
            audio_out = gr.Audio(label="🔈 Assistant Audio", type="filepath", autoplay=True, streaming=True, interactive=False)

        conv_state = gr.State([])
        send_btn = gr.Button("Send to Assistant", variant="primary")

        send_btn.click(
            process_voice_message,
            inputs=[audio_in, conv_state],
            outputs=[audio_out, chatbot],
        ).then(
            lambda chat_history: chat_history,
            inputs=[chatbot],
            outputs=[conv_state],
            api_name=None,
        )

        send_btn.click(lambda: None, None, [audio_in], api_name=None)

        demo.launch()

    return demo

if __name__ == "__main__":
    build_app()