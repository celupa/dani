# TODO: audio stream is delayed until processing, need to find a way to stream
# audio as it comes in 
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

def _history_to_messages(history: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Convert a Gradio Chatbot history (type='messages') to the format
    expected by the OpenAI Chat Completions API.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # copy every message verbatim in the order they were produced.
    # gradio already stores them as {"role": "...", "content": "..."}.
    for m in history:
        # ignore empty placeholders that may sneak in
        if m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})

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
    """Fetch response from llm (gpt-4o-mini). Also includes streaming."""

    # convert gradio history to openai messages
    messages = _history_to_messages(conversation)
    
    # fetch llm response through api
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=512,
        temperature=0.7,
        stream=True
    )
    
    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

def prompt_tts(text: str) -> str:
    """convert llm text output to speech (gpt-4o-mini-tts, onyx voice)."""

    # stream openai tts response to WAV file
    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="onyx",
        input=text,
        response_format="wav",
    ) as response:
        for chunk in resp.iter_bytes(chunk_size=4096):
            yield chunk          # each chunk goes straight to the frontend
        # out_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        # response.stream_to_file(out_path)
        # return out_path

def process_voice_message(
    audio: Optional[str],
    chat_history: List[Dict[str, str]],
) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    """string the stt-llm-tts pipeline together."""

    if audio is None:
        yield None, chat_history
        return

    # transcribe speech to text
    try:
        user_text = prompt_stt(audio)
    except Exception as e:
        chat_history.append(
            {"role": "assistant",
             "content": "The assistant has unexpectedly gone blind. Please reach out to your local developper."}
        )
        print(e)
        yield None, chat_history
        return

    chat_history.append({"role": "user", "content": user_text})
    yield gr.update(), chat_history

    # get llm response
    assistant_text = ""
    try:
        assistant_text = ""                       # we build this up chunk by chunk
        for delta in prompt_llm(_history_to_messages(chat_history)):
            assistant_text += delta

            # if the assistant message already exists, overwrite it; else append
            if chat_history and chat_history[-1]["role"] == "assistant":
                chat_history[-1]["content"] = assistant_text
            else:
                chat_history.append({"role": "assistant", "content": assistant_text})

            # push partial text to UI
            yield gr.update(), chat_history
    except Exception as e:
        chat_history.append(
             {"role": "assistant",
             "content": "The assistant just suffered an aneurysm. Please reach out to your local developper."}
            )
        print(e)
        return None, chat_history

    # chat_history.append({"role": "assistant", "content": assistant_text})

    # get text to speech
    try:
        for chunk in prompt_tts(assistant_text):
            # first positional output is audio_out, second is chatbot
            yield chunk, chat_history   # chat history is unchanged here
        # audio_reply = prompt_tts(assistant_text)
    except Exception as e:
        chat_history.append(
            {"role": "assistant",
             "content": "The assistant's tongue has swollen to a point where it cannot talk. Please reach out to your local developper."}
        )
        print(e)
        audio_reply = None 

    yield gr.update(value=audio_reply, autoplay=True), chat_history

def build_app() -> gr.Blocks:
    # show send button and clear assistant output on new recording
    def _on_new_audio(audio_path: str):
        visible = bool(audio_path)
        return gr.update(visible=visible), None  # clear audio_out
    
    def _check_access_token(token: str) -> Tuple[gr.update, gr.update, str]:
        """
        Check if user token is valid. If it is, provide app access.
        
        returns
            login_screen visibility
            app_screen visibility
            access_token_input warning
            """
        valid_token = "yup"
        if token == valid_token:
            return gr.update(visible=False), gr.update(visible=True), None
        return gr.update(visible=True), gr.update(visible=False), gr.update(label="Invalid Token! Reach out to andrei.lupascu@hotmail.be to get one")
    
    # gradio app
    with gr.Blocks(title="Voice Chatbot") as demo:
        gr.Markdown("# Ready to take your english to the next level? Let's chat!")

        # we start with a login screen to not blow up my API credits
        login_screen = gr.Column(visible=True)
        with login_screen:
            access_token_input = gr.Text(label="Enter your access token here")
            submit_token_btn =gr.Button("Connect")

        # the app screen contains chatbot and recording fields 
        app_screen = gr.Column(visible=False)
        with app_screen:
            # text area
            chatbot = gr.Chatbot(label="Conversation", height=400, type="messages")

            # recording and audio output area
            audio_in = gr.Audio(
                sources=["microphone"],
                type="filepath",
                label="🎤 Record / Play",
                format="wav"
            )
            audio_out = gr.Audio(
            label="🔈 Assistant Audio", 
            type="filepath", 
            autoplay=True, 
            streaming=True, 
            interactive=False
            )
            # store app state
            conv_state = gr.State([])
            # after recording, send speech data to assistant for processing
            send_btn = gr.Button("Send to Assistant", variant="primary", visible=False)
            # display send_btn only when user recorded something
            audio_in.change(
                _on_new_audio,
                inputs=audio_in,
                outputs=[send_btn, audio_out],
            )
        
        # check user has correct access token    
        submit_token_btn.click(
            lambda token: _check_access_token("yup"), 
            inputs=[access_token_input], 
            outputs=[login_screen, app_screen, access_token_input])
        
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

        # queue app for streaming 
        # TODO, what is queue, anyway?
        demo.queue()
        demo.launch()

    return demo

if __name__ == "__main__":
    build_app()