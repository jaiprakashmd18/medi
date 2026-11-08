"use client";

/**
 * Voice tutor primitives built on the browser Web Speech API:
 * text-to-speech (speechSynthesis) and speech-to-text (SpeechRecognition).
 * Everything runs in the browser; availability depends on the browser
 * (Chrome/Edge support both; Firefox supports synthesis only).
 */
import { useCallback, useEffect, useRef, useState } from "react";

export function speakableText(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/\[(\d+(?:\s*[,–-]\s*\d+)*)\]/g, "")
    .replace(/[#*_`>|]/g, " ")
    .replace(/\(AI explanation\)/gi, "")
    .replace(/-{3,}/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function useSpeechSynthesis(rate = 1, voiceName?: string | null) {
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);

  useEffect(() => {
    if (!supported) return;
    const load = () => setVoices(window.speechSynthesis.getVoices());
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", load);
      window.speechSynthesis.cancel();
    };
  }, [supported]);

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setSpeakingId(null);
    setPaused(false);
  }, [supported]);

  const speak = useCallback((id: string, text: string, onEnd?: () => void) => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    // split into sentences so long answers don't hit engine limits
    const parts = speakableText(text).match(/[^.!?]+[.!?]*/g) ?? [];
    const voice = voices.find((v) => v.name === voiceName) ?? voices.find((v) => v.lang.startsWith("en")) ?? null;
    parts.forEach((p, i) => {
      const u = new SpeechSynthesisUtterance(p.trim());
      u.rate = rate;
      if (voice) u.voice = voice;
      if (i === parts.length - 1) u.onend = () => { setSpeakingId(null); setPaused(false); onEnd?.(); };
      window.speechSynthesis.speak(u);
    });
    setSpeakingId(id);
    setPaused(false);
  }, [supported, rate, voiceName, voices]);

  const pause = useCallback(() => { window.speechSynthesis.pause(); setPaused(true); }, []);
  const resume = useCallback(() => { window.speechSynthesis.resume(); setPaused(false); }, []);

  return { supported, speak, stop, pause, resume, speakingId, paused, voices };
}

type Recognition = {
  lang: string; interimResults: boolean; continuous: boolean;
  onresult: ((e: any) => void) | null; onend: (() => void) | null; onerror: ((e: any) => void) | null;
  start: () => void; stop: () => void;
};

export function useSpeechRecognition(onFinal: (text: string) => void) {
  const Ctor = typeof window !== "undefined"
    ? ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition) : null;
  const supported = !!Ctor;
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<Recognition | null>(null);
  const cb = useRef(onFinal);
  cb.current = onFinal;

  const start = useCallback(() => {
    if (!Ctor) return;
    setError(null);
    const rec: Recognition = new Ctor();
    rec.lang = "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (e: any) => {
      let fin = "";
      let tmp = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) fin += t; else tmp += t;
      }
      setInterim(tmp);
      if (fin.trim()) cb.current(fin.trim());
    };
    rec.onerror = (e: any) => setError(e.error === "not-allowed" ? "Microphone permission denied." : `Speech recognition error: ${e.error}`);
    rec.onend = () => { setListening(false); setInterim(""); };
    recRef.current = rec;
    rec.start();
    setListening(true);
  }, [Ctor]);

  const stop = useCallback(() => { recRef.current?.stop(); setListening(false); }, []);
  return { supported, listening, interim, error, start, stop };
}
