import { useEffect, useRef, useState } from 'react';

interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: ArrayLike<{
    isFinal: boolean;
    0: { transcript: string };
  }>;
}

interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

function recognitionConstructor(): SpeechRecognitionConstructor | null {
  const speechWindow = window as typeof window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition || null;
}

function recognitionLanguage(language: string): string {
  if (language === 'en') return 'en-US';
  if (language === 'zh-TW') return 'zh-TW';
  return 'zh-CN';
}

interface Options {
  language: string;
  onTranscript: (transcript: string) => void;
}

export function useSpeechInput({ language, onTranscript }: Options) {
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const callbackRef = useRef(onTranscript);
  const [listening, setListening] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [failed, setFailed] = useState(false);
  const supported = typeof window !== 'undefined' && Boolean(recognitionConstructor());
  callbackRef.current = onTranscript;

  useEffect(() => () => recognitionRef.current?.abort(), []);

  const toggle = () => {
    if (listening) {
      setProcessing(true);
      recognitionRef.current?.stop();
      return;
    }
    const Recognition = recognitionConstructor();
    if (!Recognition) return;
    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = recognitionLanguage(language);
    recognition.onresult = (event) => {
      let finalText = '';
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        if (event.results[index].isFinal) finalText += event.results[index][0].transcript;
      }
      if (finalText.trim()) callbackRef.current(finalText.trim());
    };
    recognition.onerror = () => {
      setFailed(true);
      setListening(false);
      setProcessing(false);
    };
    recognition.onend = () => {
      setListening(false);
      setProcessing(false);
    };
    recognitionRef.current = recognition;
    setFailed(false);
    setListening(true);
    recognition.start();
  };

  return { supported, listening, processing, failed, toggle };
}
