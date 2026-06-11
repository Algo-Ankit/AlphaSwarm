'use client'
import { useState, useEffect } from 'react'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import type { LLMConfig, LLMConfigCreate } from '@/lib/types'
import { Brain, Trash2, Plus, ChevronDown, ChevronUp, Eye, EyeOff, XCircle, CheckCircle2 } from 'lucide-react'
import { cn } from '@/lib/utils'

// ── Provider metadata ────────────────────────────────────────────────────────

const PROVIDERS = [
  { id: 'groq',      label: 'Groq',      color: 'from-orange-400 to-orange-600',  defaultUrl: 'https://api.groq.com/openai/v1',    hint: 'Free tier: 14,400 req/day. Fast inference.', models: ['llama-3.1-8b-instant', 'llama-3.1-70b-versatile', 'mixtral-8x7b-32768'] },
  { id: 'openai',    label: 'OpenAI',    color: 'from-emerald-400 to-teal-600',   defaultUrl: 'https://api.openai.com/v1',          hint: 'GPT-4o, GPT-4 Turbo. Best code quality.',    models: ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo'] },
  { id: 'together',  label: 'Together',  color: 'from-blue-400 to-indigo-600',    defaultUrl: 'https://api.together.xyz/v1',        hint: 'Free $25 credit on signup.',                 models: ['meta-llama/Llama-3-8b-chat-hf', 'mistralai/Mixtral-8x7B-Instruct-v0.1'] },
  { id: 'anthropic', label: 'Anthropic', color: 'from-violet-400 to-purple-600',  defaultUrl: 'https://api.anthropic.com/v1',       hint: 'Claude 3.5 Haiku, Claude 3 Opus.',           models: ['claude-3-5-haiku-20241022', 'claude-3-5-sonnet-20241022'] },
  { id: 'custom',    label: 'Custom',    color: 'from-zinc-400 to-zinc-600',      defaultUrl: '',                                   hint: 'Any OpenAI-compatible endpoint.',            models: [] },
] as const

type ProviderId = (typeof PROVIDERS)[number]['id']

function providerMeta(id: string) {
  return PROVIDERS.find((p) => p.id === id) ?? PROVIDERS[PROVIDERS.length - 1]
}

// ── Config Card ──────────────────────────────────────────────────────────────

function ConfigCard({ config, onDelete }: { config: LLMConfig; onDelete: (id: string) => void }) {
  const [deleting, setDeleting] = useState(false)
  const meta = providerMeta(config.provider)

  async function handleDelete() {
    setDeleting(true)
    try {
      await api.deleteLLMConfig(config.id)
      onDelete(config.id)
    } catch {
      setDeleting(false)
    }
  }

  return (
    <GlassCard padding="none" className="overflow-hidden">
      <div className="flex items-center gap-4 px-6 py-5">
        <div className={cn('flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-sm bg-gradient-to-br', meta.color)}>
          {meta.label[0]}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[15px] font-semibold text-zinc-900 dark:text-zinc-100">{config.label}</span>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-widest bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400">
              {meta.label}
            </span>
          </div>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-0.5 font-mono">{config.key_preview}</p>
          <p className="text-xs text-zinc-400 mt-0.5 truncate">{config.model}</p>
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-500/10 transition-colors disabled:opacity-40 flex-shrink-0"
        >
          <Trash2 className="w-3.5 h-3.5" />
          Remove
        </button>
      </div>
    </GlassCard>
  )
}

// ── Add Form ─────────────────────────────────────────────────────────────────

function AddConfigForm({ onAdded }: { onAdded: (c: LLMConfig) => void }) {
  const [open, setOpen] = useState(false)
  const [provider, setProvider] = useState<ProviderId>('groq')
  const [label, setLabel]       = useState('')
  const [baseUrl, setBaseUrl]   = useState('https://api.groq.com/openai/v1')
  const [apiKey, setApiKey]     = useState('')
  const [model, setModel]       = useState('llama-3.1-8b-instant')
  const [showKey, setShowKey]   = useState(false)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)

  function handleProviderChange(id: ProviderId) {
    const meta = providerMeta(id)
    setProvider(id)
    setBaseUrl(meta.defaultUrl)
    setModel(meta.models[0] ?? '')
    setLabel(meta.label)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const config = await api.addLLMConfig({ label, provider, base_url: baseUrl, api_key: apiKey, model })
      onAdded(config)
      setApiKey('')
      setOpen(false)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Save failed'
      try { setError(JSON.parse(msg)?.detail ?? msg) } catch { setError(msg) }
    } finally {
      setLoading(false)
    }
  }

  const meta = providerMeta(provider)

  return (
    <GlassCard padding="none" className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-6 py-5 hover:bg-zinc-50/50 dark:hover:bg-white/[0.03] transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-gradient-to-br from-violet-500 to-violet-700 text-white flex-shrink-0">
            <Plus className="w-4 h-4" />
          </div>
          <div className="text-left">
            <p className="text-[15px] font-semibold text-zinc-900 dark:text-zinc-100">Add LLM Key</p>
            <p className="text-xs text-zinc-500 mt-0.5">Groq, OpenAI, Together, Anthropic, or custom endpoint</p>
          </div>
        </div>
        {open ? <ChevronUp className="w-5 h-5 text-zinc-400" /> : <ChevronDown className="w-5 h-5 text-zinc-400" />}
      </button>

      <div className={cn('grid transition-all duration-300 ease-in-out', open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0')}>
        <div className="overflow-hidden">
          <form onSubmit={handleSubmit} className="px-6 pb-6 pt-4 border-t border-black/[0.05] dark:border-white/[0.05] space-y-5">

            {/* Provider selector */}
            <div>
              <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Provider</label>
              <div className="grid grid-cols-5 gap-2">
                {PROVIDERS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleProviderChange(p.id as ProviderId)}
                    className={cn(
                      'py-2 rounded-xl text-xs font-semibold border transition-all',
                      provider === p.id
                        ? 'border-violet-500 bg-violet-50 dark:bg-violet-500/15 text-violet-700 dark:text-violet-300'
                        : 'border-zinc-200 dark:border-zinc-700 text-zinc-500 hover:border-zinc-300 dark:hover:border-zinc-600',
                    )}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              {meta.hint && (
                <p className="text-xs text-zinc-400 mt-1.5">{meta.hint}</p>
              )}
            </div>

            {/* Label */}
            <div>
              <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Label</label>
              <input
                type="text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="e.g. My Groq Key"
                required
                className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-violet-500/30 transition-shadow"
              />
            </div>

            {/* Model */}
            <div>
              <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Model</label>
              {meta.models.length > 0 ? (
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-violet-500/30 transition-shadow"
                >
                  {meta.models.map((m) => <option key={m} value={m}>{m}</option>)}
                  <option value="__custom__">Custom model name…</option>
                </select>
              ) : null}
              {(meta.models.length === 0 || model === '__custom__') && (
                <input
                  type="text"
                  value={model === '__custom__' ? '' : model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="e.g. llama-3.1-8b-instant"
                  required
                  className={cn(
                    'w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm font-mono text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-violet-500/30 transition-shadow',
                    meta.models.length > 0 && 'mt-2',
                  )}
                />
              )}
            </div>

            {/* Base URL */}
            <div>
              <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Base URL</label>
              <input
                type="url"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                required
                className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl px-4 py-3 text-sm font-mono text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-violet-500/30 transition-shadow"
              />
            </div>

            {/* API Key */}
            <div>
              <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">API Key</label>
              <div className="relative">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-…"
                  required
                  autoComplete="new-password"
                  spellCheck={false}
                  className="w-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl px-4 py-3 pr-11 text-sm font-mono text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-violet-500/30 transition-shadow"
                />
                <button type="button" onClick={() => setShowKey(!showKey)} className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300" tabIndex={-1}>
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-100 dark:border-zinc-700/50">
              <div className="w-1.5 h-1.5 rounded-full bg-violet-500 flex-shrink-0" />
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                Keys are encrypted with AES-256 before storage and never returned via the API.
              </p>
            </div>

            {error && (
              <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20">
                <XCircle className="w-4 h-4 text-rose-500 mt-0.5 flex-shrink-0" />
                <p className="text-sm font-medium text-rose-600 dark:text-rose-400">{error}</p>
              </div>
            )}

            <Button type="submit" loading={loading} disabled={!apiKey.trim() || !model.trim() || model === '__custom__' && !model.trim()} className="w-full">
              {!loading && <CheckCircle2 className="w-4 h-4 mr-2" />}
              {loading ? 'Saving…' : 'Save Key'}
            </Button>
          </form>
        </div>
      </div>
    </GlassCard>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function AISettingsPage() {
  const [configs, setConfigs] = useState<LLMConfig[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.listLLMConfigs()
      .then(setConfigs)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto animate-slide-up relative z-10 pb-20">
        <div className="mb-10">
          <h1 className="text-3xl font-extrabold text-zinc-900 dark:text-zinc-100 tracking-tight">AI Models</h1>
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            Add your own LLM API keys to unlock better models for NL strategy generation. The platform provides a free Groq tier by default.
          </p>
        </div>

        {/* Platform default */}
        <section className="mb-8">
          <h2 className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-3">Platform Default</h2>
          <GlassCard padding="none" className="overflow-hidden">
            <div className="flex items-center gap-4 px-6 py-5">
              <div className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-sm bg-gradient-to-br from-orange-400 to-orange-600">G</div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[15px] font-semibold text-zinc-900 dark:text-zinc-100">Groq (Platform Key)</span>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-widest bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300">Free</span>
                </div>
                <p className="text-xs text-zinc-400 mt-0.5">llama-3.1-8b-instant · Always available · No setup required</p>
              </div>
            </div>
          </GlassCard>
        </section>

        {/* User configs */}
        {!loading && configs.length > 0 && (
          <section className="mb-8">
            <h2 className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-3">Your Keys</h2>
            <div className="space-y-3">
              {configs.map((c) => (
                <ConfigCard key={c.id} config={c} onDelete={(id) => setConfigs((prev) => prev.filter((x) => x.id !== id))} />
              ))}
            </div>
          </section>
        )}

        {loading && <div className="flex items-center justify-center py-16 text-zinc-400 text-sm">Loading…</div>}

        {/* Add form */}
        {!loading && (
          <section>
            <h2 className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-3">Add Key</h2>
            <AddConfigForm onAdded={(c) => setConfigs((prev) => [...prev, c])} />
          </section>
        )}

        <div className="mt-10 flex items-start gap-3 px-5 py-4 rounded-2xl bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-200/60 dark:border-zinc-700/40">
          <Brain className="w-4 h-4 text-violet-500 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">
            Your keys are used only for strategy generation — not stored in model training or shared with other users. You can add multiple keys and switch between them per strategy.
          </p>
        </div>
      </div>
    </AppShell>
  )
}
