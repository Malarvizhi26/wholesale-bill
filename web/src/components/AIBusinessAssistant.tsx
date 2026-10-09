import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles,
  Send,
  Bot,
  User,
  TrendingUp,
  CheckCircle2,
  ExternalLink,
  ShieldCheck,
  Languages,
} from 'lucide-react';
import type { Language, AIQueryResponse, SuggestedQuery } from '../types';
import { api } from '../api/client';

interface AIBusinessAssistantProps {
  language: Language;
  onNavigateTab?: (tab: 'pos' | 'dashboard' | 'inventory' | 'ledger' | 'reports', subtab?: string) => void;
}

interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text?: string;
  response?: AIQueryResponse;
  timestamp: Date;
}

export const AIBusinessAssistant: React.FC<AIBusinessAssistantProps> = ({
  language,
  onNavigateTab,
}) => {
  const [queryInput, setQueryInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [suggestions, setSuggestions] = useState<SuggestedQuery[]>([]);
  const [preferredLang, setPreferredLang] = useState<'both' | 'ta' | 'en'>('both');
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Load suggested queries on mount
  useEffect(() => {
    const loadSuggestions = async () => {
      try {
        const sugs = await api.getAISuggestions();
        setSuggestions(sugs);
      } catch {
        // fallback suggestions
      }
    };
    loadSuggestions();

    // Welcome greeting
    const welcomeEn = "வணக்கம்! I am your AI Business Assistant. Ask questions like 'Which products made the most profit this month?', 'Who owes me money?', or 'Which items should I reorder?'";
    const welcomeTa = "வணக்கம்! நான் உங்கள் ஹார்டுவேர் கடை உதவியாளர். 'இந்த மாதம் அதிக லாபம் தந்த பொருட்கள் எவை?', 'யாருக்கு கடன் பாக்கி உள்ளது?', அல்லது 'எந்த பொருட்களை மீண்டும் ஆர்டர் செய்ய வேண்டும்?' என்று கேட்கலாம்.";

    setMessages([
      {
        id: 'welcome',
        sender: 'assistant',
        response: {
          query: 'வணக்கம்',
          detected_intent: 'general_help',
          tool_called: 'none',
          tool_parameters: {},
          answer_en: welcomeEn,
          answer_ta: welcomeTa,
          data_card: null,
          action_link: null,
          suggested_queries: [],
        },
        timestamp: new Date(),
      },
    ]);
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async (queryText?: string) => {
    const textToSend = (queryText ?? queryInput).trim();
    if (!textToSend || loading) return;

    const userMsgId = Date.now().toString();
    const newUserMsg: ChatMessage = {
      id: userMsgId,
      sender: 'user',
      text: textToSend,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, newUserMsg]);
    setQueryInput('');
    setLoading(true);

    try {
      const response = await api.askAIAssistant(textToSend, preferredLang);
      const assistantMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: 'assistant',
        response,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: 'assistant',
        response: {
          query: textToSend,
          detected_intent: 'error',
          tool_called: 'none',
          tool_parameters: {},
          answer_en: `Sorry, unable to process query: ${err?.message || 'Server connection error.'}`,
          answer_ta: `மன்னிக்கவும், தகவல் பெறுவதில் பிழை: ${err?.message || 'சர்வர் இணைப்பு கிடைக்கவில்லை.'}`,
          data_card: null,
          action_link: null,
          suggested_queries: [],
        },
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleActionClick = (route: string) => {
    if (!onNavigateTab) return;
    if (route.startsWith('/reports')) {
      const subtab = route.includes('tab=margin')
        ? 'margin'
        : route.includes('tab=daily')
        ? 'daily'
        : route.includes('tab=valuation')
        ? 'valuation'
        : 'overview';
      onNavigateTab('reports', subtab);
    } else if (route.startsWith('/ledger')) {
      onNavigateTab('ledger');
    } else if (route.startsWith('/inventory')) {
      onNavigateTab('inventory');
    } else if (route.startsWith('/pos')) {
      onNavigateTab('pos');
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-4 space-y-4">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 p-5 rounded-2xl border border-slate-700/80 shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center text-white shadow-lg shadow-emerald-950/60 ring-2 ring-emerald-400/20">
            <Sparkles className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-black text-white tracking-tight">
                {language === 'ta' ? 'AI வணிக உதவியாளர்' : 'AI Business Assistant'}
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-mono font-bold border border-emerald-500/30 flex items-center gap-1">
                <ShieldCheck className="w-3 h-3 text-emerald-400" />
                Zero SQL Hallucination
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              {language === 'ta'
                ? 'லாபம், வாடிக்கையாளர் கடன் பாக்கி மற்றும் சரக்கு மறுஆர்டர் தகவல்களை உடனடியாகக் கேளுங்கள்'
                : 'Deterministic domain tool execution for profits, receivables, reorders & dead stock'}
            </p>
          </div>
        </div>

        {/* Language Preference Filter */}
        <div className="flex items-center gap-1.5 bg-slate-800/90 p-1 rounded-xl border border-slate-700">
          <Languages className="w-4 h-4 text-slate-400 ml-1.5" />
          <button
            onClick={() => setPreferredLang('both')}
            className={`text-xs px-2.5 py-1 rounded-lg font-semibold transition ${
              preferredLang === 'both' ? 'bg-emerald-600 text-white shadow' : 'text-slate-400 hover:text-white'
            }`}
          >
            Bilingual (இருமொழியும்)
          </button>
          <button
            onClick={() => setPreferredLang('ta')}
            className={`text-xs px-2.5 py-1 rounded-lg font-semibold transition ${
              preferredLang === 'ta' ? 'bg-emerald-600 text-white shadow' : 'text-slate-400 hover:text-white'
            }`}
          >
            தமிழ்
          </button>
          <button
            onClick={() => setPreferredLang('en')}
            className={`text-xs px-2.5 py-1 rounded-lg font-semibold transition ${
              preferredLang === 'en' ? 'bg-emerald-600 text-white shadow' : 'text-slate-400 hover:text-white'
            }`}
          >
            English
          </button>
        </div>
      </div>

      {/* Suggested Prompt Chips */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 whitespace-nowrap pl-1 flex items-center gap-1">
          <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
          {language === 'ta' ? 'பரிந்துரை கேள்விகள்:' : 'Quick Questions:'}
        </span>
        {suggestions.map((sug, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(sug.query)}
            disabled={loading}
            className="text-xs whitespace-nowrap px-3 py-1.5 rounded-xl bg-slate-800/90 hover:bg-slate-750 text-slate-200 hover:text-emerald-300 border border-slate-700 hover:border-emerald-500/50 transition flex items-center gap-1.5 shadow-sm active:scale-95"
          >
            <span>{language === 'ta' ? sug.label_ta : sug.label_en}</span>
          </button>
        ))}
      </div>

      {/* Chat Messages Stream */}
      <div className="hardware-card p-4 h-[560px] flex flex-col justify-between space-y-4">
        <div className="flex-1 overflow-y-auto space-y-4 pr-1 scrollbar-thin">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex items-start gap-3 ${
                msg.sender === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              {msg.sender === 'assistant' && (
                <div className="w-8 h-8 rounded-lg bg-emerald-950 text-emerald-400 border border-emerald-800 flex items-center justify-center shrink-0 mt-1">
                  <Bot className="w-4 h-4" />
                </div>
              )}

              <div
                className={`max-w-3xl rounded-2xl p-4 shadow-md ${
                  msg.sender === 'user'
                    ? 'bg-emerald-600 text-white font-medium ml-12'
                    : 'bg-slate-800/90 text-slate-100 border border-slate-700 mr-4 space-y-3'
                }`}
              >
                {msg.sender === 'user' ? (
                  <div className="text-sm">{msg.text}</div>
                ) : (
                  <>
                    {/* Tool Badge */}
                    {msg.response?.tool_called && msg.response.tool_called !== 'none' && (
                      <div className="flex items-center justify-between text-[11px] text-slate-400 border-b border-slate-700/60 pb-2">
                        <span className="font-mono text-emerald-400 font-semibold flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          ⚡ Tool: {msg.response.tool_called}()
                        </span>
                        <span className="text-[10px] text-slate-500">
                          Deterministic Engine
                        </span>
                      </div>
                    )}

                    {/* Dual Language Text Answers */}
                    <div className="space-y-2">
                      {(preferredLang === 'both' || preferredLang === 'ta') && (
                        <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-750 text-sm leading-relaxed text-emerald-200/95 font-medium">
                          <div className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider mb-1 flex items-center gap-1">
                            <span>🇮🇳 தமிழ் விளக்கம்</span>
                          </div>
                          {msg.response?.answer_ta}
                        </div>
                      )}

                      {(preferredLang === 'both' || preferredLang === 'en') && (
                        <div className="text-sm leading-relaxed text-slate-200">
                          {preferredLang === 'both' && (
                            <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider mb-1">
                              🇬🇧 English Summary
                            </div>
                          )}
                          {msg.response?.answer_en}
                        </div>
                      )}
                    </div>

                    {/* Data Card (if returned) */}
                    {msg.response?.data_card && (
                      <div className="bg-slate-900/90 rounded-xl p-3 border border-slate-700 space-y-3">
                        <div className="flex items-center justify-between">
                          <h4 className="text-xs font-bold text-slate-200">
                            {language === 'ta'
                              ? msg.response.data_card.title_ta
                              : msg.response.data_card.title_en}
                          </h4>
                        </div>

                        {/* Summary Chips */}
                        {msg.response.data_card.summary_chips?.length > 0 && (
                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                            {msg.response.data_card.summary_chips.map((chip, cIdx) => (
                              <div
                                key={cIdx}
                                className="bg-slate-800/80 p-2 rounded-lg border border-slate-700 text-center"
                              >
                                <div className="text-[10px] text-slate-400">
                                  {language === 'ta' ? chip.label_ta : chip.label_en}
                                </div>
                                <div className="text-xs font-black text-emerald-400 font-mono mt-0.5">
                                  {chip.value}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Tabular Rows */}
                        {msg.response.data_card.rows?.length > 0 && (
                          <div className="overflow-x-auto max-h-60 overflow-y-auto rounded-lg border border-slate-750 scrollbar-thin">
                            <table className="w-full text-left text-xs">
                              <thead className="bg-slate-800/90 text-slate-400 sticky top-0 text-[11px] font-semibold">
                                <tr>
                                  {msg.response.data_card.columns.map((col) => (
                                    <th key={col.key} className="py-2 px-3">
                                      {language === 'ta' ? col.label_ta : col.label_en}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-800 text-slate-300">
                                {msg.response.data_card.rows.map((row, rIdx) => (
                                  <tr key={rIdx} className="hover:bg-slate-800/40">
                                    {msg.response?.data_card?.columns.map((col) => (
                                      <td key={col.key} className="py-2 px-3 font-mono text-[11px]">
                                        {col.type === 'badge' ? (
                                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                                            {row[col.key]}
                                          </span>
                                        ) : (
                                          row[col.key] ?? '-'
                                        )}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Action Link */}
                    {msg.response?.action_link && (
                      <div className="pt-1 flex items-center justify-end">
                        <button
                          onClick={() => handleActionClick(msg.response!.action_link!.route)}
                          className="text-xs px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold flex items-center gap-1.5 shadow transition active:scale-95"
                        >
                          <span>
                            {language === 'ta'
                              ? msg.response.action_link.label_ta
                              : msg.response.action_link.label_en}
                          </span>
                          <ExternalLink className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}

                    {/* Follow-up suggestions */}
                    {msg.response?.suggested_queries?.length ? (
                      <div className="flex items-center gap-1.5 flex-wrap pt-2 border-t border-slate-750">
                        <span className="text-[10px] text-slate-500 font-bold uppercase">
                          {language === 'ta' ? 'அடுத்த கேள்வி:' : 'Related:'}
                        </span>
                        {msg.response.suggested_queries.map((sq, sqIdx) => (
                          <button
                            key={sqIdx}
                            onClick={() => handleSend(sq.query)}
                            className="text-[11px] px-2 py-0.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-emerald-300 border border-slate-700 transition"
                          >
                            {language === 'ta' ? sq.label_ta : sq.label_en}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </>
                )}
                <div className="text-[10px] text-slate-500 text-right mt-1">
                  {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>

              {msg.sender === 'user' && (
                <div className="w-8 h-8 rounded-lg bg-slate-800 text-slate-300 border border-slate-700 flex items-center justify-center shrink-0 mt-1">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-950 text-emerald-400 border border-emerald-800 flex items-center justify-center shrink-0 mt-1">
                <Bot className="w-4 h-4" />
              </div>
              <div className="bg-slate-800/90 rounded-2xl p-4 border border-slate-700 text-xs text-slate-400 flex items-center gap-2">
                <div className="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-emerald-400"></div>
                <span>Executing domain tool & generating dual-language cards...</span>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Query Input Bar */}
        <div className="pt-2 border-t border-slate-800 flex items-center gap-2">
          <input
            type="text"
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSend();
            }}
            placeholder={
              language === 'ta'
                ? "கேள்வி கேட்கவும் (எ.கா: 'யாருக்கு கடன் பாக்கி உள்ளது?', 'அதிக லாபம் தந்த பொருள் எவை?')..."
                : "Ask question (e.g. 'Which products made the most profit?', 'Who owes me money?')..."
            }
            className="flex-1 bg-slate-900 border border-slate-700 focus:border-emerald-500 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 transition"
          />

          <button
            onClick={() => handleSend()}
            disabled={!queryInput.trim() || loading}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold px-4 py-2.5 rounded-xl text-sm flex items-center gap-2 shadow-lg shadow-emerald-950/60 transition active:scale-95 shrink-0"
          >
            <span>{language === 'ta' ? 'அனுப்புக' : 'Ask'}</span>
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
