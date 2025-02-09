# the following program is provided by DevMiser - https://github.com/DevMiser

import boto3
import openai
import os
import pvcobra
import pvleopard
import pvporcupine
import pyaudio
import random
import struct
import sys
import textwrap
import threading
import time
import wave

from os import environ
environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

from colorama import Fore, Style
from pvleopard import *
from pvrecorder import PvRecorder
from threading import Thread, Event
from time import sleep


audio_stream = None
cobra = None
pa = None
polly = boto3.client('polly')
porcupine = None
recorder = None
wav_file = None

GPT_model = "gpt-3.5-turbo-1106" # most capable GPT-3.5 model and optimized for chat
openai.api_key = "put your secret API key between these quotation marks"
pv_access_key= "put your secret access key between these quotation marks"

prompt = ["How may I assist you?",
    "How may I help?",
    "What can I do for you?",
    "Ask me anything.",
    "Yes?",
    "I'm here.",
    "I'm listening.",
    "What would you like me to do?"]

chat_log=[
    {"role": "system", "content": "あなたの名前はjarvisです。 あなたは役に立つAIアシスタントです。"},
    ]

def ChatGPT(query):
    if not query.strip() or len(query) <= 7:
        return "メッセージが短すぎます。もう少し具体的な質問をしてください。"
    
    user_query=[
        {"role": "user", "content": query},
        ]
    send_query = (chat_log + user_query)
    response = openai.ChatCompletion.create(
    model=GPT_model,
    messages=send_query
    )
    answer = response.choices[0]['message']['content']
    chat_log.append({"role": "assistant", "content": answer})
    return answer

def responseprinter(chat):
    wrapper = textwrap.TextWrapper(width=70)  # Adjust the width to your preference
    paragraphs = res.split('\n')
    wrapped_chat = "\n".join([wrapper.fill(p) for p in paragraphs])
    for word in wrapped_chat:
       time.sleep(0.055)
       print(word, end="", flush=True)
    print()

#DaVinci will 'remember' earlier queries so that it has greater continuity in its response
#the following will delete that 'memory' five minutes after the start of the conversation
def append_clear_countdown():
    sleep(300)
    global chat_log
    chat_log.clear()
    chat_log=[
        {"role": "system", "content": "あなたの名前はjarvisです。 あなたは役に立つAIアシスタントです。"},
        ]    
    global count
    count = 0
    t_count.join

def voice(chat):
    voiceResponse = polly.synthesize_speech(Text=chat, OutputFormat="mp3",
                    VoiceId="Matthew") #other options include Amy, Joey, Nicole, Raveena and Russell
    if "AudioStream" in voiceResponse:
        with voiceResponse["AudioStream"] as stream:
            output_file = "speech.mp3"
            try:
                with open(output_file, "wb") as file:
                    file.write(stream.read())
            except IOError as error:
                print(error)

    else:
        print("did not work")

    pygame.mixer.init()     
    pygame.mixer.music.load(output_file)
#    pygame.mixer.music.set_volume(0.8) # uncomment to control the the playback volume (from 0.0 to 1.0  
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pass
    sleep(0.2)

def wake_word():

    porcupine = pvporcupine.create(keywords=["computer", "jarvis", "DaVinci",],
                            access_key=pv_access_key,
                            sensitivities=[1, 1, 0.1], #from 0 to 1.0 - a higher number reduces the miss rate at the cost of increased false alarms
                                   )
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    sys.stderr.flush()
    os.dup2(devnull, 2)
    os.close(devnull)
    
    wake_pa = pyaudio.PyAudio()

    porcupine_audio_stream = wake_pa.open(
                    rate=porcupine.sample_rate,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=porcupine.frame_length)
    
    Detect = True
    print("waiting...")
    while Detect:
        porcupine_pcm = porcupine_audio_stream.read(porcupine.frame_length)
        porcupine_pcm = struct.unpack_from("h" * porcupine.frame_length, porcupine_pcm)

        porcupine_keyword_index = porcupine.process(porcupine_pcm)

        if porcupine_keyword_index >= 0:

            print(Fore.GREEN + "\nWake word detected\n")
            porcupine_audio_stream.stop_stream
            porcupine_audio_stream.close()
            porcupine.delete()         
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
            Detect = False

def listen():

    cobra = pvcobra.create(access_key=pv_access_key)

    listen_pa = pyaudio.PyAudio()

    listen_audio_stream = listen_pa.open(
                rate=cobra.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=cobra.frame_length)

    print("Listening...")

    while True:
        listen_pcm = listen_audio_stream.read(cobra.frame_length)
        listen_pcm = struct.unpack_from("h" * cobra.frame_length, listen_pcm)
           
        if cobra.process(listen_pcm) > 0.3:
            print("Voice detected")
            listen_audio_stream.stop_stream
            listen_audio_stream.close()
            cobra.delete()
            break

def detect_silence():

    cobra = pvcobra.create(access_key=pv_access_key)

    silence_pa = pyaudio.PyAudio()

    cobra_audio_stream = silence_pa.open(
                    rate=cobra.sample_rate,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=cobra.frame_length)

    last_voice_time = time.time()

    while True:
        cobra_pcm = cobra_audio_stream.read(cobra.frame_length)
        cobra_pcm = struct.unpack_from("h" * cobra.frame_length, cobra_pcm)
           
        if cobra.process(cobra_pcm) > 0.2:
            last_voice_time = time.time()
        else:
            silence_duration = time.time() - last_voice_time
            if silence_duration > 1.3:
                print("End of query detected\n")
                cobra_audio_stream.stop_stream                
                cobra_audio_stream.close()
                cobra.delete()
                last_voice_time=None
                break
                
def to_file(audio):
    """ 
    write_audio_to_file: Write audio to file with wave library.
    """
    with wave.open("audio.wav", 'w') as f:
        f.setparams((1, 2, 16000, len(audio), "NONE", "NONE"))
        f.writeframes(struct.pack("h" * len(audio), *audio))

def stt():
    audio_file = open("audio.wav", "rb")
    text = openai.Audio.transcribe("whisper-1", audio_file, 
                                          response_format="text")
    return text

class Recorder(Thread):
    def __init__(self):
        super().__init__()
        self._pcm = list()
        self._is_recording = False
        self._stop = False

    def is_recording(self):
        return self._is_recording

    def run(self):
        self._is_recording = True

        recorder = PvRecorder(device_index=-1, frame_length=512)
        recorder.start()

        while not self._stop:
            self._pcm.extend(recorder.read())
        recorder.stop()

        self._is_recording = False

    def stop(self):
        self._stop = True
        while self._is_recording:
            pass

        return self._pcm

try:

    o = create(
        access_key=pv_access_key,
        enable_automatic_punctuation = True,
        )
    
    event = threading.Event()

    count = 0

    while True:
        
        try:
        
            if count == 0:
                t_count = threading.Thread(target=append_clear_countdown)
                t_count.start()
            else:
                pass   
            count += 1
            wake_word()
# comment out the next line if you do not want DaVinci to respond to his name        
            voice(random.choice(prompt))
            recorder = Recorder()
            recorder.start()
            listen()
            detect_silence()
            #transcript, words = o.process(recorder.stop())
            to_file(recorder.stop())
            transcript=stt()
            recorder.stop()
            print(transcript)
#            voice(transcript) # uncomment to have DaVinci repeat what it heard
            (res) = ChatGPT(transcript)
            print("\nChatGPT's response is:\n")        
            t1 = threading.Thread(target=voice, args=(res,))
            t2 = threading.Thread(target=responseprinter, args=(res,))
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            event.set()       
            recorder.stop()
            o.delete
            recorder = None

        except openai.error.APIError as e:
            print("\nThere was an API error.  Please try again in a few minutes.")
            voice("\nThere was an A P I error.  Please try again in a few minutes.")
            event.set()     
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)

        except openai.error.Timeout as e:
            print("\nYour request timed out.  Please try again in a few minutes.")
            voice("\nYour request timed out.  Please try again in a few minutes.")
            event.set()     
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)

        except openai.error.RateLimitError as e:
            print("\nYou have hit your assigned rate limit.")
            voice("\nYou have hit your assigned rate limit.")
            event.set()     
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)

        except openai.error.APIConnectionError as e:
            print("\nI am having trouble connecting to the API.  Please check your network connection and then try again.")
            voice("\nI am having trouble connecting to the A P I.  Please check your network connection and try again.")
            event.set()     
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)

        except openai.error.AuthenticationError as e:
            print("\nYour OpenAI API key or token is invalid, expired, or revoked.  Please fix this issue and then restart my program.")
            voice("\nYour Open A I A P I key or token is invalid, expired, or revoked.  Please fix this issue and then restart my program.")
            event.set()     
            recorder.stop()
            o.delete
            recorder = None
            break

        except openai.error.ServiceUnavailableError as e:
            print("\nThere is an issue with OpenAI’s servers.  Please try again later.")
            voice("\nThere is an issue with Open A I’s servers.  Please try again later.")
            event.set()        
            recorder.stop()
            o.delete
            recorder = None
            sleep(1)
        
except KeyboardInterrupt:
    print("\nExiting ChatGPT Virtual Assistant")
    o.delete
