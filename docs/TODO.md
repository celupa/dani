TODO
- DB (Sqlite): 
    - access_keys
    - student_nickname
    - student_access_key
- UI (Gradio):
    - Access:
        - Please enter your access key (UUID)
            - Check DB for access key
            - If exists proceed to app, if not go to Setup page
            - If valid, proceed.
    - Setup:
        - Hello, my name is Dani, your english instructor. Let's get to know each other!
        - What should I call you?
        - Care to share a few of your interests?
        - ~~What language are you trying to perfect?~~
        - If you're having difficulties in our english conversations, in what language would you like me to respond? (e.g., french, romanian)
    - App
        - Text and audio
- Audio
    - May need to either use a different audio plugin or containerize app (had to sudo apt install python3-pyaudio)
- Optimization
    - Why are we using wave file instead of mp3 or any other format?
    - Look into optimizing/compressing audiofiles
- Cleanup
    - Make sure audiofiles are deleted on user machine (both in /tmp and /tmp/gradio)

Features
- STT
- LLM
- TTS

Checks
- Microphone software for deployment
- User Microphone functionality
- Integrity of audio file

Pricing: 
- see dani_api_pricing.xlsx

Beyond
- DB: 
    - setup student data (interests)
- UI:
    - 
- Features
    - Implement multilinguality for app UI
    - Implement language check for the STT-LLM-TTS-Pipeline (does it exist?)
    - Memory (assess students levels, interests and level over time)
- LLM
    -  Extend instruction capabilities (allow users to define personality and assistant name...)
