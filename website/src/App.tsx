import { useState } from 'react'
import './App.css'

const GITHUB_URL = 'https://github.com/Angeall/speks'
const DEMO_URL = import.meta.env.VITE_DEMO_URL || ''

function Navbar() {
  return (
    <nav className="navbar">
      <div className="navbar-inner">
        <a href="#" className="navbar-brand">
          <img src="/logo.svg" alt="Speks" />
          Speks
        </a>
        <ul className="navbar-links">
          <li><a href="#features">Features</a></li>
          <li><a href="#tags">Tags</a></li>
          <li><a href="#demo">Demo</a></li>
          <li><a href="#examples">Examples</a></li>
        </ul>
        <a href={GITHUB_URL} className="navbar-cta" target="_blank" rel="noopener">
          <GitHubIcon /> GitHub
        </a>
      </div>
    </nav>
  )
}

function Hero() {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText('pip install speks')
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section className="hero section">
      <div className="hero-bg" />
      <div className="hero-badge">
        <span className="hero-badge-dot" />
        Open Source &middot; Apache 2.0
      </div>
      <h1>
        Documentation that<br />
        <span className="gradient">actually runs</span>
      </h1>
      <p className="hero-subtitle">
        Turn business rules into interactive, testable specifications.
        Write pseudo-code, embed it in Markdown, and generate a live website
        where stakeholders can read, understand, and <strong>test</strong> every rule.
      </p>
      <div className="hero-actions">
        <a href="#demo" className="btn-primary">
          See it in action <ArrowDown />
        </a>
        <a href={`${GITHUB_URL}#quick-start`} className="btn-secondary" target="_blank" rel="noopener">
          Get started
        </a>
      </div>
      <div className="hero-install" onClick={handleCopy} title="Click to copy">
        <span>$</span> pip install speks
        <span className="copy-hint">{copied ? 'Copied!' : 'click to copy'}</span>
      </div>
    </section>
  )
}

function CodePreview() {
  return (
    <section className="code-preview section">
      <div className="code-preview-grid">
        <div className="code-panel">
          <div className="code-panel-label">
            <span className="dot green" /> src/rules.py
          </div>
          <pre>{pythonCode()}</pre>
        </div>
        <div className="code-panel">
          <div className="code-panel-label">
            <span className="dot blue" /> docs/credit-rules.md
          </div>
          <pre>{markdownCode()}</pre>
        </div>
      </div>
    </section>
  )
}

function pythonCode() {
  return (
    <>
      <span className="kw">from</span> speks <span className="kw">import</span> ExternalService, MockResponse{'\n'}
      {'\n'}
      {'\n'}
      <span className="kw">class</span> <span className="cls">CheckBalance</span>(ExternalService):{'\n'}
      {'    '}<span className="str">"""Core Banking API call."""</span>{'\n'}
      {'\n'}
      {'    '}<span className="kw">def</span> <span className="fn">execute</span>(self, client_id: str) -&gt; float:{'\n'}
      {'        '}<span className="kw">pass</span>  <span className="cm"># real HTTP in prod</span>{'\n'}
      {'\n'}
      {'    '}<span className="kw">def</span> <span className="fn">mock</span>(self, client_id: str) -&gt; MockResponse:{'\n'}
      {'        '}<span className="kw">return</span> MockResponse(data=<span className="num">1500.0</span>){'\n'}
      {'\n'}
      {'\n'}
      <span className="kw">def</span> <span className="fn">evaluate_credit</span>(client_id: str, amount: float) -&gt; bool:{'\n'}
      {'    '}<span className="str">"""Client balance must exceed amount."""</span>{'\n'}
      {'    '}balance = CheckBalance().call(client_id){'\n'}
      {'    '}<span className="kw">return</span> balance &gt; amount{'\n'}
    </>
  )
}

function markdownCode() {
  return (
    <>
      <span className="cm"># Credit Evaluation</span>{'\n'}
      {'\n'}
      <span className="cm">## Contract</span>{'\n'}
      <span className="tag">@[contract]</span>(src/rules.py:evaluate_credit){'\n'}
      {'\n'}
      <span className="cm">## Source Code</span>{'\n'}
      <span className="tag">@[code]</span>(src/rules.py:evaluate_credit){'\n'}
      {'\n'}
      <span className="cm">## Try it Live</span>{'\n'}
      <span className="tag">@[playground]</span>(src/rules.py:evaluate_credit){'\n'}
      {'\n'}
      <span className="cm">## Execution Flow</span>{'\n'}
      <span className="tag">@[sequence]</span>(src/rules.py:evaluate_credit){'\n'}
      {'\n'}
      <span className="cm">## Dependencies</span>{'\n'}
      <span className="tag">@[dependencies]</span>(src/){'\n'}
      {'\n'}
      <span className="cm">## Decision Flow</span>{'\n'}
      <span className="tag">@[mermaid]</span>(diagrams/flow.mmd){'\n'}
    </>
  )
}

const features = [
  {
    icon: '▶',
    color: 'purple',
    title: 'Interactive Playground',
    desc: 'Every function gets an auto-generated form. Test business rules live in the browser — no setup, no CLI needed.',
  },
  {
    icon: '◆',
    color: 'blue',
    title: 'Smart Mocking',
    desc: 'External services are auto-mocked. Override values, simulate errors, and inspect every service call in real time.',
  },
  {
    icon: '⬡',
    color: 'green',
    title: 'Auto-generated Diagrams',
    desc: 'Dependency graphs and sequence diagrams generated from static analysis of your code. Always in sync.',
  },
  {
    icon: '✓',
    color: 'orange',
    title: 'Test Case Management',
    desc: 'Save, replay, and validate test scenarios directly from the documentation. Your specs become regression tests.',
  },
  {
    icon: '⊞',
    color: 'pink',
    title: '7 Markdown Tags',
    desc: '@[code], @[playground], @[contract], @[dependencies], @[sequence], @[mermaid], @[plantuml] — embed live content anywhere.',
  },
  {
    icon: '⬢',
    color: 'indigo',
    title: 'Standalone Binaries',
    desc: 'Distribute as a single executable for Windows, macOS, and Linux. No Python installation required.',
  },
]

function Features() {
  return (
    <section className="features section" id="features">
      <div className="section-header">
        <div className="section-label">Features</div>
        <h2 className="section-title">Everything you need for<br />living documentation</h2>
        <p className="section-subtitle">
          From interactive playgrounds to auto-generated diagrams, Speks turns static specs into executable contracts.
        </p>
      </div>
      <div className="features-grid">
        {features.map((f) => (
          <div className="feature-card" key={f.title}>
            <div className={`feature-icon ${f.color}`}>{f.icon}</div>
            <h3>{f.title}</h3>
            <p>{f.desc}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

const tags = [
  { tag: '@[code](src/file.py:func)', desc: 'Embed function source code with syntax highlighting' },
  { tag: '@[playground](src/file.py:func)', desc: 'Interactive form to test the function live in the browser' },
  { tag: '@[contract](src/file.py:func)', desc: 'Function signature rendered as a readable table (inputs, outputs, types)' },
  { tag: '@[dependencies](src/)', desc: 'Auto-generated dependency graph as a Mermaid flowchart' },
  { tag: '@[sequence](src/file.py:func)', desc: 'Auto-generated sequence diagram from the function control flow' },
  { tag: '@[mermaid](diagrams/flow.mmd)', desc: 'Embed a Mermaid diagram from a .mmd file' },
  { tag: '@[plantuml](diagrams/file.puml)', desc: 'Embed a PlantUML diagram rendered as SVG' },
]

function Tags() {
  return (
    <section className="tags section" id="tags">
      <div className="section-header">
        <div className="section-label">Markdown Tags</div>
        <h2 className="section-title">Seven tags to rule them all</h2>
        <p className="section-subtitle">
          Extend Markdown with special tags that generate live, interactive content from your source code.
        </p>
      </div>
      <div className="tags-table-wrapper">
        <table className="tags-table">
          <thead>
            <tr>
              <th>Tag</th>
              <th>What it generates</th>
            </tr>
          </thead>
          <tbody>
            {tags.map((t) => (
              <tr key={t.tag}>
                <td><code>{t.tag}</code></td>
                <td>{t.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Demo() {
  return (
    <section className="demo section" id="demo">
      <div className="section-header">
        <div className="section-label">Live Demo</div>
        <h2 className="section-title">See Speks in action</h2>
        <p className="section-subtitle">
          This is a real Speks-generated documentation site embedded below.
          Try clicking the playground to test business rules.
        </p>
      </div>
      <div className="demo-container">
        <div className="demo-topbar">
          <div className="demo-dots">
            <div className="demo-dot" />
            <div className="demo-dot" />
            <div className="demo-dot" />
          </div>
          <div className="demo-url">{DEMO_URL || 'localhost:8000'} — speks serve</div>
        </div>
        <div className="demo-iframe-wrapper">
          {DEMO_URL ? (
            <iframe
              src={DEMO_URL}
              title="Speks Live Demo"
              className="demo-iframe"
              sandbox="allow-scripts allow-same-origin allow-forms"
            />
          ) : (
            <div className="demo-placeholder">
              <div className="demo-placeholder-icon">&#9654;</div>
              <p>Run <code>cd examples/credit-evaluation && speks serve</code> and<br />the demo will appear here on <code>localhost:8000</code></p>
            </div>
          )}
        </div>
      </div>
      <p className="demo-hint">
        Run <code>speks serve</code> for the interactive playground with live execution.
      </p>
    </section>
  )
}

const examples = [
  {
    emoji: '🏦',
    title: 'Credit Evaluation',
    desc: 'Balance checks, credit scoring, compliance verification, and multi-service orchestration.',
    tag: 'Banking',
    path: 'examples/credit-evaluation',
  },
  {
    emoji: '🛒',
    title: 'Order Processing',
    desc: 'Volume pricing, loyalty discounts, inventory checks, and payment processing.',
    tag: 'E-commerce',
    path: 'examples/order-processing',
  },
  {
    emoji: '🏥',
    title: 'Patient Eligibility',
    desc: 'Insurance verification, cost estimation, prior authorization workflows.',
    tag: 'Healthcare',
    path: 'examples/patient-eligibility',
  },
  {
    emoji: '🚚',
    title: 'Shipping Calculator',
    desc: 'Zone-based rates, weight surcharges, delivery estimation, customs clearance.',
    tag: 'Logistics',
    path: 'examples/shipping-calculator',
  },
]

function Examples() {
  return (
    <section className="examples section" id="examples">
      <div className="section-header">
        <div className="section-label">Examples</div>
        <h2 className="section-title">Built for every industry</h2>
        <p className="section-subtitle">
          Complete example projects showing Speks in action across different domains.
        </p>
      </div>
      <div className="examples-grid">
        {examples.map((ex) => (
          <a
            href={`${GITHUB_URL}/tree/main/${ex.path}`}
            className="example-card"
            key={ex.title}
            target="_blank"
            rel="noopener"
          >
            <div className="example-emoji">{ex.emoji}</div>
            <h3>{ex.title}</h3>
            <p>{ex.desc}</p>
            <span className="example-tag">{ex.tag}</span>
          </a>
        ))}
      </div>
    </section>
  )
}

function CTA() {
  return (
    <section className="cta section">
      <div className="cta-box">
        <h2>Your specs should run,<br />not rot.</h2>
        <p>
          Get started in under a minute. Speks is free, open source, and built for teams
          that care about living documentation.
        </p>
        <div className="cta-actions">
          <a href={`${GITHUB_URL}#quick-start`} className="btn-primary" target="_blank" rel="noopener">
            Get started
          </a>
          <a href={GITHUB_URL} className="btn-secondary" target="_blank" rel="noopener">
            <GitHubIcon /> Star on GitHub
          </a>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer className="footer">
      <div className="footer-inner">
        <span className="footer-text">Speks — Open Source (Apache 2.0)</span>
        <ul className="footer-links">
          <li><a href={GITHUB_URL} target="_blank" rel="noopener">GitHub</a></li>
          <li><a href={`${GITHUB_URL}/issues`} target="_blank" rel="noopener">Issues</a></li>
          <li><a href={`${GITHUB_URL}/blob/main/CONTRIBUTING.md`} target="_blank" rel="noopener">Contributing</a></li>
          <li><a href={`${GITHUB_URL}/blob/main/LICENSE`} target="_blank" rel="noopener">License</a></li>
        </ul>
      </div>
    </footer>
  )
}

function App() {
  return (
    <div className="app">
      <Navbar />
      <Hero />
      <CodePreview />
      <Features />
      <Tags />
      <Demo />
      <Examples />
      <CTA />
      <Footer />
    </div>
  )
}

/* ── Icons ─────────────────────────────────────────────────────────────── */

function GitHubIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
    </svg>
  )
}

function ArrowDown() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <polyline points="19 12 12 19 5 12" />
    </svg>
  )
}

export default App
