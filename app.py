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
    """
    convert arbitrary audio to 16kHz mono WAV (openai's preferred format).
    whisper can ingest many formats, but providing a consistent WAV
    eliminates edge cases.  
    
    returns
        path to the converted file (which may equal the input if conversion was unnecessary).
    """

    # read file
    sound = AudioSegment.from_file(audio_path)

    # if file is already perfect
    if sound.frame_rate == 16000 and sound.channels == 1 and audio_path.lower().endswith(".wav"):
        return audio_path
    
    # otherwise convert to wav
    converted = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sound.set_frame_rate(16000).set_channels(1).export(converted.name, format="wav")

    return converted.name

def _history_to_messages(history: Sequence[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """convert gr.Chatbot format to openai chat messages."""

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # iterate over previous messages and append them messages
    for user_prompt, llm_response in history:
        messages.append({"role": "user", "content": user_prompt})
        if llm_response:
            messages.append({"role": "assistant", "content": llm_response})

    return messages

def prompt_stt(audio_filepath: str) -> str:
    """transcribe sound to text (using whisper)."""

    # convert file to WAV format
    wav_path = _ensure_wav(audio_filepath)

    # leverage openai api (whipser)
    with open(wav_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",
        )

    return response.strip()

def prompt_llm(conversation: List[Tuple[str, str]]) -> str:
    """fetch response from llm (gpt-4o-mini)."""

    # convert gradio history to openai messages
    messages = _history_to_messages(conversation)
    
    # fetch llm response through api
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=512,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()

def prompt_tts(text: str) -> str:
    """convert llm text output to speech (gpt-4o-mini-tts, onyx voice)."""

    # stream openai tts response to WAV file
    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="onyx",
        input=text,
        response_format="wav",
    ) as response:
        out_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        response.stream_to_file(out_path)

        return out_path

def process_voice_message(
    audio: Optional[str],
    chat_history: List[Tuple[str, str]],
) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    """string the stt-llm-tts pipeline together."""

    if audio is None:
        return None, chat_history

    # transcribe speech to text
    try:
        user_text = prompt_stt(audio)
    except Exception as e:
        chat_history.append(("<STT error>", "Speech-to-text response is broke! Reach out to your local developper."))
        print(e)
        return None, chat_history

    # if stt succesful append user prompt and placeholder to chat
    chat_history.append((user_text, ""))

    # get llm response
    try:
        assistant_text = prompt_llm(chat_history)
    except Exception as e:
        # chat_history[-1] = (user_text, "LLM response is broken! Reach out to your local developper.")
        chat_history.append(("<LLM error>", "LLM response is broke! Reach out to your local developper."))
        print(e)
        return None, chat_history

    # if llm prompts succesful replace last entry by user prompt and llm resposne
    chat_history[-1] = (user_text, assistant_text)

    # get text to speech
    try:
        audio_reply = prompt_tts(assistant_text)
    except Exception as e:
        chat_history.append(("<TTS error>", "Text-to-speech response is broke! Reach out to your local developper."))
        print(e)
        audio_reply = None 

    return audio_reply, chat_history

def build_app() -> gr.Blocks:
    # show send button and clear assistant output on new recording
    def _on_new_audio(audio_path: str):
        visible = bool(audio_path)
        return gr.update(visible=visible), None  # clear audio_out
    
    # gradio app
    with gr.Blocks(title="Voice Chatbot") as demo:
        gr.Markdown("## 🎙️ Voice Chatbot with STT → LLM → TTS")

        chatbot = gr.Chatbot(label="Conversation", height=400)

        audio_out = gr.Audio(
        label="🔈 Assistant Audio", 
        type="filepath", 
        autoplay=True, 
        streaming=True, 
        interactive=False
        )

        audio_in = gr.Audio(
            sources=["microphone"],
            type="filepath",
            label="🎤 Record / Play",
            format="wav",
        )

        conv_state = gr.State([])

        send_btn = gr.Button("Send to Assistant", variant="primary", visible=False)

        # display send_btn only when user recorded something
        audio_in.change(
            _on_new_audio,
            inputs=audio_in,
            outputs=[send_btn, audio_out],
        )

        # initiate stt-llm-tts pipeline
        send_chain = send_btn.click(
            process_voice_message,
            inputs=[audio_in, conv_state],
            outputs=[audio_out, chatbot],
        )

        # update hidden conv_state with latest chat history
        send_chain.then(lambda chat: chat, inputs=[chatbot], outputs=[conv_state])

        # hide send button until next recording
        send_chain.then(lambda: gr.update(visible=False), None, [send_btn])

        demo.launch()

    return demo

if __name__ == "__main__":
    build_app()
